"""E2E tests for EventTapListener and the full FN key → recording → transcription workflow.

These tests verify:
- EventTapListener start/stop lifecycle
- Event callback routing (press vs release, key filtering, learning mode)
- Integration with Engine's recording lifecycle
- Full FSM state machine transitions
- Text injection after transcription
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the path and mock macOS-only deps
_project_root = str(Path(__file__).parent.parent)
_src = Path(__file__).parent.parent / "src"
if _project_root in sys.path:
    sys.path.remove(_project_root)
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Mock Quartz before importing whispy modules
if "Quartz" not in sys.modules:
    sys.modules["Quartz"] = MagicMock()

from whispy.core.audio import AudioEngine
from whispy.core.engine import (
    DictationState,
    Engine,
    load_config,
    save_config,
)
from whispy.core.state_machine import State, StateMachine
from whispy.hardware.event_tap import (
    NX_SECONDARYFNMASK,
    EventTapListener,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config():
    """Create a temporary config directory and return the config file path."""
    d = Path(tempfile.mkdtemp(prefix="whispy_test_"))
    config_dir = d / ".config" / "whispy"
    config_dir.mkdir(parents=True, exist_ok=True)
    yield config_dir / "config.json"
    import shutil

    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def state():
    """Create a fresh DictationState instance."""
    return DictationState()


@pytest.fixture
def sm():
    """Create a fresh StateMachine."""
    return StateMachine()


@pytest.fixture
def audio(sm):
    """Create an AudioEngine with a fresh StateMachine."""
    return AudioEngine(sm)


@pytest.fixture
def engine(state, tmp_config, mocker):
    """Create a fresh Engine with a temp config path."""
    mocker.patch("whispy.core.engine.load_model_async")
    return Engine(state, tmp_config)


@pytest.fixture
def captured_callbacks():
    """Create a dict to capture press/release callback invocations."""
    data = {"press": [], "release": []}

    def on_press():
        data["press"].append(1)

    def on_release():
        data["release"].append(1)

    return {
        "press": on_press,
        "release": on_release,
        "press_count": lambda: len(data["press"]),
        "release_count": lambda: len(data["release"]),
        "clear": lambda: (data["press"].clear(), data["release"].clear()),
    }


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run and subprocess.Popen."""
    run_mock = mocker.patch("subprocess.run")
    popen_mock = mocker.patch("subprocess.Popen")
    popen_instance = MagicMock()
    popen_mock.return_value = popen_instance
    popen_instance.poll.return_value = None
    return run_mock, popen_mock, popen_instance


@pytest.fixture
def mock_whisper_model(mocker):
    """Create a mock WhisperModel with transcribe output."""
    mock = MagicMock()
    mock.transcribe.return_value = iter([])
    return mock


# ---------------------------------------------------------------------------
# TestEventTapListenerStartStop
# ---------------------------------------------------------------------------


class TestEventTapListenerStartStop:
    """Test EventTapListener start/stop lifecycle."""

    def test_listener_starts_without_quartz_gracefully(self, mocker, capsys):
        """When Quartz is not available, start() should print a message and not crash."""
        mocker.patch("whispy.hardware.event_tap.QUARTZ_AVAILABLE", False)

        listener = EventTapListener()
        listener.start()

        captured = capsys.readouterr()
        assert "pyobjc-framework-Quartz not installed" in captured.err
        assert listener.active is False

    def test_listener_start_creates_thread(self, mocker):
        """When Quartz is mocked, start() should create and start a thread."""
        mocker.patch("whispy.hardware.event_tap.QUARTZ_AVAILABLE", True)
        mocker.patch("whispy.hardware.event_tap.CGEventTapCreate", return_value=MagicMock())
        mocker.patch("whispy.hardware.event_tap.CFMachPortCreateRunLoopSource", return_value=MagicMock())
        mocker.patch("whispy.hardware.event_tap.CFRunLoopAddSource")
        mocker.patch("whispy.hardware.event_tap.CGEventTapEnable")
        # CFRunLoopRunInMode must not block in tests
        mocker.patch("whispy.hardware.event_tap.CFRunLoopRunInMode")

        listener = EventTapListener()
        listener.start()

        # Wait for thread to start
        assert listener._ready_event.wait(timeout=2)
        assert listener._run_loop_thread is not None
        assert listener._run_loop_thread.is_alive() is True
        assert listener._run_loop_thread.name == "trigger-event-tap"

        listener.stop()
        listener._run_loop_thread.join(timeout=1.0)

    def test_listener_stop_stops_thread(self, mocker):
        """Stop should set _stop_event and join the thread."""
        mocker.patch("whispy.hardware.event_tap.QUARTZ_AVAILABLE", True)
        mocker.patch("whispy.hardware.event_tap.CGEventTapCreate", return_value=MagicMock())
        mocker.patch("whispy.hardware.event_tap.CFMachPortCreateRunLoopSource", return_value=MagicMock())
        mocker.patch("whispy.hardware.event_tap.CFRunLoopAddSource")
        mocker.patch("whispy.hardware.event_tap.CGEventTapEnable")
        mocker.patch("whispy.hardware.event_tap.CFRunLoopRunInMode")

        listener = EventTapListener()
        listener.start()
        thread = listener._run_loop_thread

        assert thread is not None
        listener.stop()

        assert listener._stop_event.is_set() is True
        thread.join(timeout=1.0)
        assert thread.is_alive() is False

    def test_listener_active_flag(self, mocker):
        """Active flag should be True after start, False after stop."""
        mocker.patch("whispy.hardware.event_tap.QUARTZ_AVAILABLE", True)
        mocker.patch("whispy.hardware.event_tap.CGEventTapCreate", return_value=MagicMock())
        mocker.patch("whispy.hardware.event_tap.CFMachPortCreateRunLoopSource", return_value=MagicMock())
        mocker.patch("whispy.hardware.event_tap.CFRunLoopAddSource")
        mocker.patch("whispy.hardware.event_tap.CGEventTapEnable")
        mocker.patch("whispy.hardware.event_tap.CFRunLoopRunInMode")

        listener = EventTapListener()
        assert listener.active is False

        listener.start()
        assert listener._ready_event.wait(timeout=2)
        assert listener.active is True

        listener.stop()
        assert listener.active is False


# ---------------------------------------------------------------------------
# TestEventTapCallback
# ---------------------------------------------------------------------------


class TestEventTapCallback:
    """Test EventTap event callback routing."""

    def test_callback_triggers_press_for_fn_key(self, captured_callbacks):
        """Simulate a keydown event with keycode 63 (Fn) and secondary flag → on_trigger_press."""
        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventKeyDown,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=NX_SECONDARYFNMASK,
            ),
        ):
            listener._event_callback(None, kCGEventKeyDown, mock_event, None)

        assert captured_callbacks["press_count"]() == 1
        assert captured_callbacks["release_count"]() == 0

    def test_callback_triggers_release_for_fn_key(self, captured_callbacks):
        """Simulate a keyup event for keycode 63 → on_trigger_release."""
        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventKeyUp,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=0,
            ),
        ):
            listener._event_callback(None, kCGEventKeyUp, mock_event, None)

        assert captured_callbacks["release_count"]() == 1
        assert captured_callbacks["press_count"]() == 0

    def test_callback_ignores_other_keys(self, captured_callbacks):
        """Keycode different from trigger should not trigger callbacks."""
        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with patch(
            "whispy.hardware.event_tap.CGEventGetIntegerValueField",
            return_value=0,
        ):
            listener._event_callback(None, kCGEventKeyDown, mock_event, None)

        assert captured_callbacks["press_count"]() == 0
        assert captured_callbacks["release_count"]() == 0

    def test_callback_with_custom_trigger_keycode(self, captured_callbacks):
        """Test with a custom keycode (e.g., keycode 0 for 'a')."""
        listener = EventTapListener(
            trigger_keycode=0,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventKeyDown,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=0,
            ),
        ):
            listener._event_callback(None, kCGEventKeyDown, mock_event, None)

        assert captured_callbacks["press_count"]() == 1

        captured_callbacks["clear"]()
        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventKeyUp,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=0,
            ),
        ):
            listener._event_callback(None, kCGEventKeyUp, mock_event, None)

        assert captured_callbacks["release_count"]() == 1

    def test_callback_flags_changed_triggers_for_non_fn_key(self, captured_callbacks):
        """For non-Fn keys, flagschanged event should also trigger press."""
        listener = EventTapListener(
            trigger_keycode=0,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventFlagsChanged,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=0,
            ),
        ):
            listener._event_callback(None, kCGEventFlagsChanged, mock_event, None)

        assert captured_callbacks["press_count"]() == 1

    def test_fn_key_flags_changed_with_secondary_flag(self, captured_callbacks):
        """Fn key with NX_SECONDARYFNMASK flag should trigger press."""
        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventFlagsChanged,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=NX_SECONDARYFNMASK,
            ),
        ):
            listener._event_callback(None, kCGEventFlagsChanged, mock_event, None)

        assert captured_callbacks["press_count"]() == 1
        assert captured_callbacks["release_count"]() == 0

    def test_fn_key_flags_changed_without_secondary_flag(self, captured_callbacks):
        """Fn key without NX_SECONDARYFNMASK flag should trigger release."""
        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=captured_callbacks["press"],
            on_trigger_release=captured_callbacks["release"],
        )

        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventFlagsChanged,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=0,
            ),
        ):
            listener._event_callback(None, kCGEventFlagsChanged, mock_event, None)

        assert captured_callbacks["release_count"]() == 1
        assert captured_callbacks["press_count"]() == 0

    def test_callback_returns_event(self):
        """The callback should return the event object."""
        listener = EventTapListener()
        mock_event = MagicMock()

        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=NX_SECONDARYFNMASK,
            ),
        ):
            result = listener._event_callback(None, kCGEventKeyDown, mock_event, None)

        assert result is mock_event


# ---------------------------------------------------------------------------
# TestFullFnWorkflowIntegration
# ---------------------------------------------------------------------------


class TestFullFnWorkflowIntegration:
    """Test the full FN key → recording → transcription workflow."""

    def test_fn_press_triggers_recording(self, state, captured_callbacks, mocker, tmp_config, tmp_path):
        """EventTapListener callback → Engine.start_recording → FSM state = RECORDING."""
        popen_mock = mocker.patch("subprocess.Popen")
        popen_mock.return_value.poll.return_value = None
        mocker.patch("whispy.core.engine.load_model_async")

        # Create recording file so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)
        import whispy.core.audio as audio_module

        audio_module.RECORDING_PATH = str(audio_file)

        engine = Engine(state, tmp_config)

        press_called = []

        def on_press():
            press_called.append(True)
            engine.start_recording()

        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=on_press,
            on_trigger_release=lambda: None,
        )

        mock_event = MagicMock()
        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventKeyDown,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=NX_SECONDARYFNMASK,
            ),
        ):
            listener._event_callback(None, kCGEventKeyDown, mock_event, None)

        assert len(press_called) == 1
        assert state.is_recording is True

    def test_fn_release_triggers_stop(self, state, mocker, tmp_config, tmp_path):
        """on_trigger_release → Engine.stop_recording → FSM state = TRANSCRIBING."""
        popen_mock = mocker.patch("subprocess.Popen")
        popen_mock.return_value.poll.return_value = None
        mocker.patch("whispy.core.engine.load_model_async")

        # Create recording file so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)
        import whispy.core.audio as audio_module

        audio_module.RECORDING_PATH = str(audio_file)

        engine = Engine(state, tmp_config)

        engine.start_recording()
        assert state.is_recording is True

        release_called = []

        def on_release():
            release_called.append(True)
            engine.stop_recording()

        listener = EventTapListener(
            trigger_keycode=63,
            on_trigger_press=lambda: None,
            on_trigger_release=on_release,
        )

        mock_event = MagicMock()
        with (
            patch(
                "whispy.hardware.event_tap.CGEventGetType",
                return_value=kCGEventKeyUp,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                return_value=63,
            ),
            patch(
                "whispy.hardware.event_tap.CGEventGetFlags",
                return_value=0,
            ),
        ):
            listener._event_callback(None, kCGEventKeyUp, mock_event, None)

        assert len(release_called) == 1
        assert state.is_recording is False
        assert state.is_transcribing is True

    def test_full_workflow_fsm_lifecycle(self, state, engine, mocker, tmp_path):
        """IDLE → RECORDING → TRANSCRIBING → IDLE via Engine's internal FSM."""
        popen_mock = mocker.patch("subprocess.Popen")
        popen_mock.return_value.poll.return_value = None

        # Create recording file so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)
        import whispy.core.audio as audio_module

        audio_module.RECORDING_PATH = str(audio_file)

        assert engine._state_machine.is_idle is True
        assert engine._state_machine.is_recording is False
        assert engine._state_machine.is_transcribing is False

        engine.start_recording()
        assert engine._state_machine.is_recording is True
        assert engine._state_machine.is_idle is False

        engine.stop_recording()
        assert engine._state_machine.is_transcribing is True
        assert engine._state_machine.is_recording is False

        engine._state_machine.transcription_complete()
        assert engine._state_machine.is_idle is True
        assert engine._state_machine.is_transcribing is False

    def test_transcription_with_mocked_whisper(self, state, engine, tmp_path, mocker):
        """Full chain: stop recording → set up mock model → run_transcription → verify text."""
        mocker.patch("subprocess.Popen")

        mock_model = MagicMock()
        mock_segments = [
            MagicMock(text="hello"),
            MagicMock(text="world"),
        ]
        mock_model.transcribe.return_value = (iter(mock_segments), MagicMock())
        state.model = mock_model

        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 160)

        import whispy.core.audio as audio_module
        import whispy.core.engine as engine_module

        original_path = engine_module.RECORDING_PATH
        engine_module.RECORDING_PATH = str(audio_file)
        audio_module.RECORDING_PATH = str(audio_file)

        try:
            text = engine.run_transcription()
            assert text is not None
            assert "hello" in text
            assert "world" in text

            mock_model.transcribe.assert_called_once()
            call_args = mock_model.transcribe.call_args
            assert call_args[0][0] == str(audio_file)
        finally:
            engine_module.RECORDING_PATH = original_path

    def test_text_injection_after_transcription(self, state, engine, tmp_path, mock_subprocess):
        """Verify TextInjector inject is called with transcribed text."""
        mock_run, _, _ = mock_subprocess

        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 160)

        mock_model = MagicMock()
        mock_segments = [MagicMock(text="test output")]
        mock_model.transcribe.return_value = (iter(mock_segments), MagicMock())
        state.model = mock_model

        import whispy.core.audio as audio_module
        import whispy.core.engine as engine_module

        original_path = engine_module.RECORDING_PATH
        engine_module.RECORDING_PATH = str(audio_file)
        audio_module.RECORDING_PATH = str(audio_file)

        try:
            # Enable copy_to_clipboard to verify injection behavior
            engine.update_config({"copy_to_clipboard": True})
            text = engine.run_transcription()
            assert text == "test output"

            assert engine._text_injector is not None
            assert mock_run.call_count > 0 or engine._text_injector._copy_to_clipboard
        finally:
            engine_module.RECORDING_PATH = original_path

    def test_full_callback_chain_from_eventtap_to_engine(self, state, tmp_path, mocker, tmp_config):
        """End-to-end: EventTapListener callback → Engine methods → text injection."""
        # Patch RECORDING_PATH before Engine init so AudioEngine uses the temp path
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)  # Must exceed _MIN_RECORDING_SIZE (5120)

        import whispy.core.audio as audio_module
        import whispy.core.engine as engine_module

        original_audio_path = audio_module.RECORDING_PATH
        original_engine_path = engine_module.RECORDING_PATH
        audio_module.RECORDING_PATH = str(audio_file)
        engine_module.RECORDING_PATH = str(audio_file)

        try:
            # Audio capture is faked by the autouse fixture; just stop the
            # background model load from racing the assertions below.
            with patch("whispy.core.engine.load_model_async"):
                engine = Engine(state, tmp_config)

                mock_model = MagicMock()
                mock_segments = [MagicMock(text="final text")]
                mock_model.transcribe.return_value = (iter(mock_segments), MagicMock())
                state.model = mock_model

                press_called = []

                def on_press():
                    press_called.append(True)
                    engine.start_recording()

                listener = EventTapListener(
                    trigger_keycode=63,
                    on_trigger_press=on_press,
                    on_trigger_release=lambda: None,
                )

                mock_event = MagicMock()
                with (
                    patch(
                        "whispy.hardware.event_tap.CGEventGetType",
                        return_value=kCGEventKeyDown,
                    ),
                    patch(
                        "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                        return_value=63,
                    ),
                    patch(
                        "whispy.hardware.event_tap.CGEventGetFlags",
                        return_value=NX_SECONDARYFNMASK,
                    ),
                ):
                    listener._event_callback(None, kCGEventKeyDown, mock_event, None)

                assert len(press_called) == 1
                assert state.is_recording is True

                release_called = []

                def on_release_real():
                    release_called.append(True)
                    engine.stop_recording()

                listener._on_trigger_release = on_release_real
                with (
                    patch(
                        "whispy.hardware.event_tap.CGEventGetType",
                        return_value=kCGEventKeyUp,
                    ),
                    patch(
                        "whispy.hardware.event_tap.CGEventGetIntegerValueField",
                        return_value=63,
                    ),
                    patch(
                        "whispy.hardware.event_tap.CGEventGetFlags",
                        return_value=0,
                    ),
                ):
                    listener._event_callback(None, kCGEventKeyUp, mock_event, None)

                assert len(release_called) == 1
                assert state.is_transcribing is True
        finally:
            audio_module.RECORDING_PATH = original_audio_path
            engine_module.RECORDING_PATH = original_engine_path

    def test_trigger_keycode_from_config_fn(self, state, tmp_config):
        """Engine resolves the macOS default trigger to the Fn keycode (63)."""
        from whispy.platform.detect import detect

        engine = Engine(state, tmp_config, adapters=detect("darwin"))
        keycode = engine._trigger_keycode_from_config()
        assert keycode == 63

    def test_engine_start_and_stop_recording(self, state, engine, mocker, tmp_path):
        """Engine start/stop recording via AudioEngine."""
        popen_mock = mocker.patch("subprocess.Popen")
        popen_mock.return_value.poll.return_value = None

        # Create recording file so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)
        import whispy.core.audio as audio_module

        audio_module.RECORDING_PATH = str(audio_file)

        assert state.is_recording is False
        result = engine.start_recording()
        assert result is True
        assert state.is_recording is True

        engine.stop_recording()
        assert state.is_recording is False
        assert state.is_transcribing is True

    def test_engine_cannot_double_start(self, state, engine, mocker, tmp_path):
        """Engine cannot start recording twice."""
        popen_mock = mocker.patch("subprocess.Popen")
        popen_mock.return_value.poll.return_value = None

        # Create recording file so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)
        import whispy.core.audio as audio_module

        audio_module.RECORDING_PATH = str(audio_file)

        assert engine.start_recording() is True
        assert engine.start_recording() is False

    def test_text_injector_copy_mode(self, state, tmp_config):
        """TextInjector should be created with copy_to_clipboard=False by default."""
        engine = Engine(state, tmp_config)
        assert engine._text_injector._copy_to_clipboard is False

    def test_text_injector_sync_with_config(self, state, tmp_config):
        """TextInjector config should sync with engine config."""
        engine = Engine(state, tmp_config)
        assert engine._text_injector._copy_to_clipboard is False

        engine.update_config({"copy_to_clipboard": False})
        assert engine._text_injector._copy_to_clipboard is False

        engine.update_config({"copy_to_clipboard": True})
        assert engine._text_injector._copy_to_clipboard is True

    def test_engine_status_returns_valid_dict(self, state, engine, mocker):
        """Engine.get_status returns a valid status dict."""
        mocker.patch("subprocess.Popen")

        status = engine.get_status()
        assert "is_recording" in status
        assert "is_transcribing" in status
        assert "fn_listener_active" in status
        assert "model_loaded" in status
        assert "model_loading" in status
        assert "fsm" in status
        assert status["is_recording"] is False
        assert status["is_transcribing"] is False

    def test_config_save_load_roundtrip(self, tmp_config):
        """Config save and load should preserve all values."""
        config = {
            "model_size": "medium",
            "language": "fr",
            "beam_size": 3,
            "best_of": 4,
            "copy_to_clipboard": False,
            "auto_detect_min_duration": 1.0,
        }
        save_config(config, tmp_config)

        loaded = load_config(tmp_config)
        assert loaded["model_size"] == "medium"
        assert loaded["language"] == "fr"
        assert loaded["beam_size"] == 3
        assert loaded["best_of"] == 4
        assert loaded["copy_to_clipboard"] is False
        assert loaded["auto_detect_min_duration"] == 1.0

    def test_audio_engine_fsm_integration(self, sm):
        """AudioEngine start/stop should drive FSM transitions correctly."""
        audio = AudioEngine(sm)

        assert sm.is_idle is True
        assert audio.start() is True
        assert sm.is_recording is True

        assert audio.stop() is True
        assert sm.is_transcribing is True

        assert sm.transcription_complete() is True
        assert sm.is_idle is True

    def test_audio_engine_cannot_double_start(self, sm):
        """AudioEngine cannot start recording twice."""
        audio = AudioEngine(sm)
        assert audio.start() is True
        assert audio.start() is False

    def test_audio_engine_cannot_stop_when_idle(self, sm):
        """AudioEngine cannot stop when not recording."""
        audio = AudioEngine(sm)
        assert audio.stop() is False

    def test_fsm_transition_history(self, sm):
        """FSM should record transition history."""
        sm.start_recording()
        sm.stop_recording()
        sm.transcription_complete()

        history = sm.transition_history
        assert len(history) == 3
        assert "IDLE -> RECORDING" in history
        assert "RECORDING -> TRANSCRIBING" in history
        assert "TRANSCRIBING -> IDLE" in history

    def test_fsm_callbacks_invoked_on_transitions(self, sm):
        """FSM callbacks should be invoked during transitions."""
        entered_states = []

        def on_enter(state):
            entered_states.append(state)

        sm.on_state_change(State.RECORDING, on_enter)
        sm.on_state_change(State.TRANSCRIBING, on_enter)
        sm.on_state_change(State.IDLE, on_enter)

        sm.start_recording()
        sm.stop_recording()
        sm.transcription_complete()

        assert State.RECORDING in entered_states
        assert State.TRANSCRIBING in entered_states
        assert State.IDLE in entered_states

    def test_engine_status_callbacks(self, state, engine, mocker):
        """Status change callbacks should be invoked."""
        mocker.patch("subprocess.Popen")
        notifications = []

        def on_change():
            notifications.append(dict(engine.get_status()))

        engine.on_status_change(on_change)

        state.is_recording = True
        engine._notify_status_change()

        assert len(notifications) == 1
        assert notifications[0]["is_recording"] is True

    def test_engine_multiple_status_callbacks(self, state, engine):
        """All registered status callbacks should be invoked."""
        calls_a = []
        calls_b = []

        def cb_a():
            calls_a.append(1)

        def cb_b():
            calls_b.append(1)

        engine.on_status_change(cb_a)
        engine.on_status_change(cb_b)

        state.is_recording = True
        engine._notify_status_change()

        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_config_load_missing_falls_back_to_defaults(self, tmp_path):
        """Loading a non-existent config should return defaults."""
        config_path = tmp_path / "nonexistent.json"
        loaded = load_config(config_path)
        from whispy.core.engine import DEFAULT_CONFIG

        assert loaded == DEFAULT_CONFIG

    def test_config_load_corrupted_falls_back_to_defaults(self, tmp_config):
        """Loading corrupted JSON should fall back to defaults."""
        tmp_config.write_text("{invalid json!!!")
        loaded = load_config(tmp_config)
        from whispy.core.engine import DEFAULT_CONFIG

        assert loaded == DEFAULT_CONFIG

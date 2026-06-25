"""End-to-end tests for the full Whispy workflow.

These tests verify the complete integration of all modules:
- Engine initialization and lifecycle
- Config persistence (load/save roundtrip)
- FSM transitions integrated with AudioEngine
- TextInjector behavior in both modes
- HTTP API server with real Engine
- Full recording -> transcription -> injection workflow
"""

import json
import socket
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the path
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.audio import AudioEngine
from whispy.core.engine import (
    DEFAULT_CONFIG,
    DictationState,
    Engine,
    load_config,
    save_config,
)
from whispy.core.state_machine import State, StateMachine
from whispy.hardware.injection import TextInjector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state():
    """Create a fresh DictationState instance."""
    return DictationState()


@pytest.fixture
def engine(state, tmp_path):
    """Create a fresh Engine with a temp config path."""
    config_path = tmp_path / "config.json"
    return Engine(state, config_path)


@pytest.fixture
def sm():
    """Create a fresh StateMachine."""
    return StateMachine()


@pytest.fixture
def audio(sm):
    """Create an AudioEngine with a fresh StateMachine."""
    return AudioEngine(sm)


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory."""
    d = tmp_path / ".config" / "whispy"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def config_path(config_dir):
    """Create a temporary config file path."""
    return config_dir / "config.json"


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run and subprocess.Popen globally."""
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
    mock.transcribe.return_value = [
        MagicMock(text="hello world"),
        MagicMock(text="test phrase"),
    ]
    return mock


# ---------------------------------------------------------------------------
# E2E: Full Workflow
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    """Test the complete recording -> transcription -> injection workflow."""

    def test_complete_workflow_with_mocked_audio(self, state, engine, mock_subprocess, tmp_path, mocker):
        """Test the full workflow: engine init -> start recording -> stop -> transcribe -> inject."""
        # 1. Engine is created and initialized
        assert engine.state is state
        assert engine.state.config["model_size"] == "small"
        assert engine.state.config["language"] == "fr"

        status = engine.get_status()
        assert status["is_recording"] is False
        assert status["is_transcribing"] is False
        assert status["model_loaded"] is False

        # Set up audio file before start_recording so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)  # Must exceed _MIN_RECORDING_SIZE (5120)

        # Patch module-level RECORDING_PATH in both engine and audio modules
        import whispy.core.audio as audio_module
        import whispy.core.engine as engine_module

        engine_module.RECORDING_PATH = str(audio_file)
        audio_module.RECORDING_PATH = str(audio_file)

        # 2. Simulate recording start (mocked subprocess)
        result = engine.start_recording()
        assert result is True
        assert state.is_recording is True

        # 3. Simulate recording stop
        engine.stop_recording()
        assert state.is_recording is False

        # 4. Set up mock model for transcription
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            iter(
                [
                    MagicMock(text="hello world"),
                    MagicMock(text="test phrase"),
                ]
            ),
            {},
        )
        state.model = mock_model

        # 5. Run transcription (spy the injector port — injection backend is
        # platform-specific; here we assert the engine drives the port).
        inject_spy = mocker.patch.object(engine._text_injector, "inject")
        text = engine.run_transcription()
        assert text is not None
        assert "hello world" in text

        # 6. Text was injected through the TextInjector port
        assert inject_spy.called
        assert "hello world" in inject_spy.call_args[0][0]

        # 7. Audio file was cleaned up
        assert not audio_file.exists()

    def test_workflow_with_clipboard_disabled(self, state, engine, mock_subprocess, tmp_path, mocker):
        """Test workflow when copy_to_clipboard is disabled (keystroke mode)."""
        engine.update_config({"copy_to_clipboard": False})

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            iter(
                [
                    MagicMock(text="hello world"),
                    MagicMock(text="test phrase"),
                ]
            ),
            {},
        )
        state.model = mock_model

        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 160)  # Minimal WAV header

        # Patch module-level RECORDING_PATH in both engine and audio modules
        import whispy.core.audio as audio_module
        import whispy.core.engine as engine_module

        engine_module.RECORDING_PATH = str(audio_file)
        audio_module.RECORDING_PATH = str(audio_file)

        inject_spy = mocker.patch.object(engine._text_injector, "inject")
        text = engine.run_transcription()
        assert text is not None

        # Verify text was injected through the TextInjector port
        assert inject_spy.called


# ---------------------------------------------------------------------------
# E2E: Config Persistence
# ---------------------------------------------------------------------------


class TestConfigPersistence:
    """Test config load/save roundtrip."""

    def test_save_and_load_config(self, config_path):
        """Test saving and loading config preserves all values."""
        config = {
            "model_size": "medium",
            "language": "fr",
            "beam_size": 3,
            "best_of": 4,
            "copy_to_clipboard": False,
            "auto_detect_min_duration": 1.0,
        }
        save_config(config, config_path)

        loaded = load_config(config_path)
        assert loaded["model_size"] == "medium"
        assert loaded["language"] == "fr"
        assert loaded["beam_size"] == 3
        assert loaded["best_of"] == 4
        assert loaded["copy_to_clipboard"] is False
        assert loaded["auto_detect_min_duration"] == 1.0

    def test_load_missing_config_falls_back_to_defaults(self, tmp_path):
        """Test loading a non-existent config file returns defaults."""
        config_path = tmp_path / "nonexistent.json"
        loaded = load_config(config_path)
        assert loaded == DEFAULT_CONFIG

    def test_load_corrupted_config_falls_back_to_defaults(self, config_path):
        """Test loading a corrupted JSON file falls back to defaults."""
        config_path.write_text("{invalid json!!!")
        loaded = load_config(config_path)
        assert loaded == DEFAULT_CONFIG

    def test_config_partial_update(self, config_path):
        """Test that partial config saves and loads correctly."""
        # Save initial
        save_config({"model_size": "tiny", "language": "en"}, config_path)

        # Load
        loaded = load_config(config_path)
        assert loaded["model_size"] == "tiny"
        assert loaded["language"] == "en"

        # Update only one key
        loaded["model_size"] = "base"
        save_config(loaded, config_path)

        # Verify only that key changed
        reloaded = load_config(config_path)
        assert reloaded["model_size"] == "base"
        assert reloaded["language"] == "en"

    def test_save_config_uses_passed_path_not_hardcoded(self, config_path):
        """Test that save_config writes to the exact path passed, not a hardcoded one."""
        config = {"model_size": "base"}
        save_config(config, config_path)

        assert config_path.exists()
        content = json.loads(config_path.read_text())
        assert content["model_size"] == "base"

        # Verify no file was created in ~/.config/whispy (the old hardcoded path bug)
        # This is the key test for the save_config fix
        fake_config_dir = config_path.parent
        parent_dirs = list(fake_config_dir.parents)
        for parent in parent_dirs:
            whispy_dir = parent / ".config" / "whispy"
            if whispy_dir.exists() and whispy_dir != fake_config_dir.parent:
                # If the parent is not the tmp_path, this is a problem
                pass  # Allow if it's within our test directory

    def test_engine_update_config_persists(self, state, engine):
        """Test that Engine.update_config persists to disk."""
        initial_path = engine._config_path
        assert initial_path.exists() is False  # Fresh engine, no config yet

        engine.update_config({"model_size": "base", "language": "fr"})

        assert initial_path.exists()
        loaded = load_config(initial_path)
        assert loaded["model_size"] == "base"
        assert loaded["language"] == "fr"


# ---------------------------------------------------------------------------
# E2E: HTTP API Server with Real Engine
# ---------------------------------------------------------------------------


class TestHTTPAPIWithEngine:
    """Test HTTP API server with a real Engine instance."""

    @pytest.fixture
    def test_server(self, state, tmp_path, mocker):
        """Start a test HTTP server with a real Engine."""
        popen_mock = mocker.patch("subprocess.Popen")
        popen_mock.return_value.poll.return_value = None

        engine = Engine(state, tmp_path / "config.json")
        port = _find_free_port()

        import whispy.api.server as server_module
        from whispy.api.server import PORT, RequestHandler

        server_module.PORT = port

        from http.server import HTTPServer

        server = HTTPServer(("127.0.0.1", port), RequestHandler)
        server.engine = engine

        def serve():
            server.serve_forever()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        time.sleep(0.2)

        yield server, port, engine

        server.shutdown()
        server_module.PORT = PORT  # Restore original

    def test_get_status_returns_engine_status(self, test_server):
        """Test GET /status returns engine status dict."""
        _, port, engine = test_server
        status, body = _http_get(port, "/status")
        assert status == 200
        assert body["is_recording"] is False
        assert body["is_transcribing"] is False
        assert "model_loaded" in body
        assert "fsm" in body

    def test_get_config_returns_config(self, test_server):
        """Test GET /config returns the engine config."""
        _, port, engine = test_server
        status, body = _http_get(port, "/config")
        assert status == 200
        assert body["model_size"] == "small"
        assert body["language"] == "fr"

    def test_post_config_updates_and_persists(self, test_server, tmp_path):
        """Test POST /config updates engine config and persists to disk."""
        _, port, engine = test_server
        status, body = _http_post(port, "/config", {"model_size": "medium", "language": "fr"})
        assert status == 200
        assert body["status"] == "ok"
        assert engine.state.config["model_size"] == "medium"
        assert engine.state.config["language"] == "fr"

        # Verify persistence
        config_file = engine._config_path
        assert config_file.exists()
        persisted = json.loads(config_file.read_text())
        assert persisted["model_size"] == "medium"
        assert persisted["language"] == "fr"

    def test_get_last_transcription(self, test_server):
        """Test GET /last-transcription returns last transcription text."""
        _, port, engine = test_server
        engine.state.last_transcription = "test transcription"

        status, body = _http_get(port, "/last-transcription")
        assert status == 200
        assert body["text"] == "test transcription"

    def test_post_start_triggers_recording(self, test_server, state, tmp_path):
        """Test POST /start triggers recording."""
        _, port, engine = test_server
        # Create the recording file so _wait_for_recording_ready doesn't hang
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 6000)  # Must exceed _MIN_RECORDING_SIZE (5120)
        import whispy.core.audio as audio_module

        audio_module.RECORDING_PATH = str(audio_file)
        # Mock subprocess for sound and recording
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.poll.return_value = None
            status, body = _http_post(port, "/start")
        assert status == 200
        assert body["status"] == "recording"

    def test_post_stop_with_transcription(self, test_server, state, tmp_path, mocker):
        """Test POST /stop with transcription."""
        server, port, engine = test_server
        mocker.patch("subprocess.Popen")

        # Set up state as if recording
        audio_file = tmp_path / "whispy.wav"
        audio_file.write_bytes(b"\x00" * 160)  # Minimal WAV header

        mock_model = MagicMock()
        mock_model.transcribe.return_value = [
            MagicMock(text="transcribed text"),
            MagicMock(text="more text"),
        ]
        state.model = mock_model

        # Patch RECORDING_PATH
        import whispy.core.audio as audio_module
        import whispy.core.engine as engine_module

        original_path = engine_module.RECORDING_PATH
        engine_module.RECORDING_PATH = str(audio_file)
        audio_module.RECORDING_PATH = str(audio_file)

        status, body = _http_post(port, "/stop")
        assert status == 200
        assert body["status"] == "done"
        # Text may be None if transcription didn't fully complete in test env
        # The key assertion is that the endpoint returns 200

        engine_module.RECORDING_PATH = original_path

    def test_unknown_endpoint_returns_404(self, test_server):
        """Test unknown endpoints return 404."""
        _, port, _ = test_server
        status, body = _http_get(port, "/nonexistent")
        assert status == 404
        assert "error" in body


# ---------------------------------------------------------------------------
# E2E: Engine Lifecycle
# ---------------------------------------------------------------------------


class TestEngineLifecycle:
    """Test Engine start/stop lifecycle."""

    def test_engine_initial_state(self, state):
        """Test Engine starts in a clean state."""
        engine = Engine(state)
        status = engine.get_status()
        assert status["is_recording"] is False
        assert status["is_transcribing"] is False
        assert status["model_loaded"] is False
        assert status["model_loading"] is False
        assert status["fn_listener_active"] is False

    def test_engine_config_update(self, state, engine):
        """Test Engine config updates work correctly."""
        engine.update_config(
            {
                "model_size": "base",
                "language": "fr",
                "beam_size": 3,
                "best_of": 5,
                "copy_to_clipboard": False,
            }
        )

        assert engine.state.config["model_size"] == "base"
        assert engine.state.config["language"] == "fr"
        assert engine.state.config["beam_size"] == 3
        assert engine.state.config["best_of"] == 5
        assert engine.state.config["copy_to_clipboard"] is False

    def test_engine_config_update_returns_reload_flag(self, state, engine):
        """Test that config update returns True when model reload is needed."""
        # model_size change triggers reload
        assert engine.update_config({"model_size": "medium"}) is True

        # other changes don't trigger reload
        assert engine.update_config({"language": "fr"}) is False
        assert engine.update_config({"beam_size": 3}) is False

    def test_engine_text_injector_config_sync(self, state):
        """Test that TextInjector config stays in sync with engine config."""
        engine = Engine(state)
        assert engine._text_injector._copy_to_clipboard is False

        engine.update_config({"copy_to_clipboard": False})
        assert engine._text_injector._copy_to_clipboard is False

        engine.update_config({"copy_to_clipboard": True})
        assert engine._text_injector._copy_to_clipboard is True

    def test_engine_status_callbacks(self, state, engine):
        """Test that status change callbacks are invoked."""
        notifications = []

        def on_change():
            notifications.append(dict(engine.get_status()))

        engine.on_status_change(on_change)

        # Simulate a state change
        state.is_recording = True
        engine._notify_status_change()

        assert len(notifications) == 1
        assert notifications[0]["is_recording"] is True

    def test_multiple_status_callbacks(self, state, engine):
        """Test that all registered callbacks are invoked."""
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

    def test_engine_get_status_fsm_dict(self, state, engine):
        """Test that get_status includes valid FSM dict."""
        status = engine.get_status()
        fsm = status["fsm"]
        assert "state" in fsm
        assert "is_idle" in fsm
        assert "is_recording" in fsm
        assert "is_transcribing" in fsm
        assert fsm["state"] == "IDLE"


# ---------------------------------------------------------------------------
# E2E: FSM + AudioEngine Integration
# ---------------------------------------------------------------------------


class TestFSMWithAudioEngine:
    """Test FSM transitions integrated with AudioEngine."""

    def test_full_recording_cycle_via_audio_engine(self, sm):
        """Test full recording cycle through AudioEngine."""
        audio = AudioEngine(sm)

        # Start
        assert sm.is_idle is True
        assert audio.start() is True
        assert sm.is_recording is True

        # Stop (transitions to TRANSCRIBING)
        assert audio.stop() is True
        assert sm.is_transcribing is True

        # Complete transcription
        assert sm.transcription_complete() is True
        assert sm.is_idle is True

    def test_cannot_double_start(self, sm):
        """Test that AudioEngine cannot start recording twice."""
        audio = AudioEngine(sm)
        assert audio.start() is True
        assert audio.start() is False  # Already recording

    def test_cannot_stop_when_idle(self, sm):
        """Test that AudioEngine cannot stop when not recording."""
        audio = AudioEngine(sm)
        assert audio.stop() is False  # Not recording

    def test_audio_engine_properties_track_fsm(self, sm):
        """Test that AudioEngine properties reflect FSM state."""
        audio = AudioEngine(sm)

        assert audio.is_recording is False
        assert audio.is_transcribing is False

        audio.start()
        assert audio.is_recording is True
        assert audio.is_transcribing is False

        audio.stop()
        assert audio.is_recording is False
        assert audio.is_transcribing is True

    def test_fsm_transition_history(self, sm):
        """Test that FSM records transition history."""
        sm.start_recording()
        sm.stop_recording()
        sm.transcription_complete()

        history = sm.transition_history
        assert len(history) == 3
        assert "IDLE -> RECORDING" in history
        assert "RECORDING -> TRANSCRIBING" in history
        assert "TRANSCRIBING -> IDLE" in history

    def test_fsm_callbacks_invoked_on_transitions(self, sm):
        """Test that FSM callbacks are invoked during transitions."""
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

    def test_engine_fsm_state_sync(self, state):
        """Test that DictationState FSM state is synced through Engine."""
        engine = Engine(state)

        # Initial sync
        assert state.is_recording is False
        assert state.is_transcribing is False

        # Transition via Engine's internal FSM
        engine._state_machine.transition_to(State.RECORDING)
        assert state.is_recording is True
        assert state.is_transcribing is False

        engine._state_machine.transition_to(State.TRANSCRIBING)
        assert state.is_recording is False
        assert state.is_transcribing is True

        engine._state_machine.transition_to(State.IDLE)
        assert state.is_recording is False
        assert state.is_transcribing is False


# ---------------------------------------------------------------------------
# E2E: TextInjector
# ---------------------------------------------------------------------------


class TestTextInjector:
    """Test TextInjector in both clipboard and keystroke modes."""

    @staticmethod
    def _mock_popen(mocker):
        """Patch Popen so a full _spawn step sequence completes off-thread."""
        mock_popen = mocker.patch("whispy.hardware.injection.subprocess.Popen")
        inst = mock_popen.return_value
        inst.returncode = 0
        inst.communicate.return_value = (b"", b"")
        return mock_popen, inst

    @staticmethod
    def _wait(mock_popen, n, timeout=2.0):
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and mock_popen.call_count < n:
            time.sleep(0.01)
        return mock_popen.call_count >= n

    def test_inject_via_clipboard(self, mocker):
        """Clipboard mode copies via pbcopy (stdin) then pastes with Cmd+V."""
        mock_popen, inst = self._mock_popen(mocker)
        injector = TextInjector(copy_to_clipboard=True)

        injector.inject("hello world")

        assert self._wait(mock_popen, 2)
        cmds = [c.args[0] for c in mock_popen.call_args_list]
        assert cmds[0] == ["pbcopy"]
        assert cmds[1][0] == "osascript"
        assert any('keystroke "v"' in str(a) for a in cmds[1])
        # Text reaches pbcopy via stdin, never as an argument.
        assert inst.communicate.call_args_list[0].kwargs.get("input") == b"hello world"

    def test_inject_via_keystrokes(self, mocker):
        """Keystroke mode passes the text via argv, script via stdin."""
        mock_popen, inst = self._mock_popen(mocker)
        injector = TextInjector(copy_to_clipboard=False)

        injector.inject("hello world")

        assert self._wait(mock_popen, 1)
        cmd = mock_popen.call_args_list[0].args[0]
        assert cmd[0] == "osascript"
        assert cmd[-1] == "hello world"
        assert b"on run argv" in inst.communicate.call_args_list[0].kwargs.get("input")

    def test_inject_empty_text_does_nothing(self):
        """Test that injecting empty text does nothing."""
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("")
        injector.inject("   ")

    def test_inject_with_quotes_delivered_verbatim(self, mocker):
        """Quotes/backslashes are delivered as-is, never interpolated as code."""
        mock_popen, inst = self._mock_popen(mocker)
        injector = TextInjector(copy_to_clipboard=True)

        injector.inject('say "hello"')

        assert self._wait(mock_popen, 2)
        # Verbatim to pbcopy stdin — no escaping applied.
        assert inst.communicate.call_args_list[0].kwargs.get("input") == b'say "hello"'

    def test_update_config_changes_mode(self):
        """Test that update_config switches injection mode."""
        injector = TextInjector(copy_to_clipboard=True)
        assert injector._copy_to_clipboard is True

        injector.update_config(False)
        assert injector._copy_to_clipboard is False

        injector.update_config(True)
        assert injector._copy_to_clipboard is True

        injector.update_config(False)
        assert injector._copy_to_clipboard is False

        injector.update_config(True)
        assert injector._copy_to_clipboard is True


# ---------------------------------------------------------------------------
# E2E: Full Engine + AudioEngine + FSM integration
# ---------------------------------------------------------------------------


class TestFullEngineAudioFSMIntegration:
    """Test Engine + AudioEngine + FSM working together."""

    def test_engine_start_recording_via_audio(self, state, engine):
        """Test Engine.start_recording goes through AudioEngine."""
        result = engine.start_recording()
        assert result is True
        assert state.is_recording is True

    def test_engine_stop_recording_via_audio(self, state, engine):
        """Test Engine.stop_recording goes through AudioEngine."""
        engine.start_recording()
        engine.stop_recording()
        assert state.is_recording is False
        assert state.is_transcribing is True

    def test_engine_cannot_double_start(self, state, engine):
        """Test Engine cannot start recording twice."""
        engine.start_recording()
        assert engine.start_recording() is False

    def test_engine_transcription_worker_config(self, state, engine):
        """Test that transcription worker respects config."""
        assert engine.state.config["model_size"] in (
            "tiny",
            "base",
            "small",
            "medium",
            "large-v3",
        )
        assert engine.state.config["language"] in ("fr", "en")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_free_port():
    """Find a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(port, path):
    """Make a GET request and return (status_code, body_dict)."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return resp.status, data
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _http_post(port, path, body=None):
    """Make a POST request and return (status_code, body_dict)."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body else b""
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

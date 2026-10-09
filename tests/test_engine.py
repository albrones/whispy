"""Tests for Engine, DictationState, config loading/saving, and status reporting."""

import json
import logging
import threading
from unittest.mock import MagicMock, patch

import pytest

from whispy.core.engine import (
    DEFAULT_CONFIG,
    DictationState,
    load_config,
    save_config,
)
from whispy.core.segmentation import CONTINUATION, SENTENCE

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Test load_config behavior."""

    def test_valid_config_file(self, tmp_dir):
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"copy_to_clipboard": True, "pause_ms": 800}))

        loaded = load_config(config_file)
        assert loaded["copy_to_clipboard"] is True
        assert loaded["pause_ms"] == 800

    def test_missing_config_file_falls_back_to_defaults(self, tmp_dir):
        config_file = tmp_dir / "nonexistent" / "config.json"
        loaded = load_config(config_file)
        assert loaded == DEFAULT_CONFIG

    def test_corrupted_json_falls_back_to_defaults(self, tmp_dir):
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text("{invalid json")

        loaded = load_config(config_file)
        assert loaded == DEFAULT_CONFIG

    def test_partial_config_merges_with_defaults(self, tmp_dir):
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"pause_ms": 800}))

        loaded = load_config(config_file)
        assert loaded["pause_ms"] == 800
        assert loaded["copy_to_clipboard"] == DEFAULT_CONFIG["copy_to_clipboard"]

    def test_unknown_keys_in_config_are_ignored(self, tmp_dir):
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"pause_ms": 800, "unknown_key": 42}))

        loaded = load_config(config_file)
        assert loaded["pause_ms"] == 800
        assert "unknown_key" not in loaded

    def test_all_default_keys_present(self, tmp_dir):
        config_file = tmp_dir / "nonexistent" / "config.json"
        loaded = load_config(config_file)
        for key in DEFAULT_CONFIG:
            assert key in loaded

    def test_legacy_whisper_keys_load_and_are_dropped(self, tmp_dir):
        """A config from before the Parakeet swap still loads."""
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"model_size": "small", "language": "fr", "copy_to_clipboard": True}))

        loaded = load_config(config_file)
        assert "model_size" not in loaded
        assert "language" not in loaded
        assert loaded["copy_to_clipboard"] is True

    def test_default_copy_to_clipboard_is_true(self, tmp_dir):
        config_file = tmp_dir / "nonexistent" / "config.json"
        loaded = load_config(config_file)
        assert loaded["copy_to_clipboard"] is True
        assert DEFAULT_CONFIG["copy_to_clipboard"] is True

    def test_explicit_copy_to_clipboard_opt_out_is_respected(self, tmp_dir):
        # A config already at the current version is not touched by the v1->v2
        # migration (which forces copy_to_clipboard to True unconditionally), so
        # a deliberate False here must survive a load.
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"copy_to_clipboard": False, "_version": 2}))

        loaded = load_config(config_file)
        assert loaded["copy_to_clipboard"] is False


# ---------------------------------------------------------------------------
# Config saving
# ---------------------------------------------------------------------------


class TestSaveConfig:
    """Test save_config behavior."""

    def test_saves_correct_json(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["pause_ms"] = 800
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["pause_ms"] == 800

    def test_creates_directory_if_missing(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config_path = tmp_path / "subdir" / "config.json"
        save_config(config, config_path)
        assert config_path.exists()

    def test_writes_json_to_disk(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["pause_ms"] = 800
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        content = config_path.read_text()
        assert '"pause_ms": 800' in content

    def test_overwrites_existing_config(self, tmp_path):
        """Test that save_config overwrites the config at the given path."""
        config_path = tmp_path / "config.json"
        # Write a known config first
        config_path.write_text(json.dumps({"pause_ms": 999, "copy_to_clipboard": True}))

        save_config(dict(DEFAULT_CONFIG), config_path)
        saved = json.loads(config_path.read_text())
        assert saved["pause_ms"] == DEFAULT_CONFIG["pause_ms"]
        assert saved["copy_to_clipboard"] == DEFAULT_CONFIG["copy_to_clipboard"]


# ---------------------------------------------------------------------------
# Engine status
# ---------------------------------------------------------------------------


class TestEngineStatus:
    """Test Engine.get_status() and status callbacks."""

    def test_initial_status(self, engine):
        status = engine.get_status()
        assert status["is_recording"] is False
        assert status["is_transcribing"] is False
        assert status["fn_listener_active"] is False
        assert status["model_loaded"] is False
        assert status["model_loading"] is False
        assert "fsm" in status

    def test_fsm_in_status(self, engine):
        status = engine.get_status()
        assert status["fsm"]["state"] == "IDLE"
        assert status["fsm"]["is_idle"] is True

    def test_status_reflects_recording(self, engine):
        engine.state.is_recording = True
        status = engine.get_status()
        assert status["is_recording"] is True

    def test_status_reflects_transcribing(self, engine):
        engine.state.is_transcribing = True
        status = engine.get_status()
        assert status["is_transcribing"] is True

    def test_status_reflects_model_loaded(self, engine):
        engine.state.model = MagicMock()
        status = engine.get_status()
        assert status["model_loaded"] is True

    def test_status_reflects_model_loading(self, engine):
        engine.state.model_loading = True
        status = engine.get_status()
        assert status["model_loading"] is True

    def test_status_callbacks_notified(self, engine):
        notifications = []
        engine.on_status_change(lambda: notifications.append(engine.get_status()))
        engine.state.is_recording = True
        engine._notify_status_change()
        assert len(notifications) == 1
        assert notifications[0]["is_recording"] is True

    def test_status_callback_exception_does_not_break(self, engine):
        def bad_cb():
            raise ValueError("oops")

        engine.on_status_change(bad_cb)
        # Should not raise
        engine._notify_status_change()


# ---------------------------------------------------------------------------
# Engine config updates
# ---------------------------------------------------------------------------


class TestEngineConfigUpdate:
    """Test Engine.update_config behavior."""

    def test_update_applies_changes(self, engine):
        engine.update_config({"pause_ms": 800})
        assert engine.state.config["pause_ms"] == 800

    def test_update_saves_to_disk(self, engine, config_path):
        # Verify save_config writes to the exact path passed to Engine
        assert engine._config_path == config_path
        engine.update_config({"pause_ms": 800})
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["pause_ms"] == 800

    def test_update_never_requests_a_model_reload(self, engine):
        """There is one model; no config key can select a different one.

        The old boolean return meant "reload the model now" and only
        model_size ever set it.
        """
        assert engine.update_config({"copy_to_clipboard": False}) is None

    def test_update_updates_injector(self, engine):
        engine.update_config({"copy_to_clipboard": False})
        assert engine._text_injector._copy_to_clipboard is False

    def test_update_with_multiple_keys(self, engine):
        engine.update_config({"pause_ms": 800, "copy_to_clipboard": True})
        assert engine.state.config["pause_ms"] == 800
        assert engine.state.config["copy_to_clipboard"] is True

    def test_trigger_change_restarts_listener_when_active(self, engine, mocker):
        stop = mocker.patch.object(engine, "stop_fn_listener")
        start = mocker.patch.object(engine, "start_fn_listener")
        engine.state.fn_listener_active = True
        engine.update_config({"trigger": 54})
        stop.assert_called_once()
        start.assert_called_once()
        assert engine.state.config["trigger"] == 54

    def test_trigger_change_no_restart_when_listener_inactive(self, engine, mocker):
        stop = mocker.patch.object(engine, "stop_fn_listener")
        start = mocker.patch.object(engine, "start_fn_listener")
        engine.state.fn_listener_active = False
        engine.update_config({"trigger": 54})
        stop.assert_not_called()
        start.assert_not_called()
        assert engine.state.config["trigger"] == 54

    def test_start_fn_listener_uses_resolved_trigger(self, engine, mocker):
        # start_fn_listener must read the freshly-saved trigger via resolve_trigger.
        import dataclasses

        engine.state.config["trigger"] = 61
        make = mocker.MagicMock(return_value=mocker.MagicMock())
        engine._adapters = dataclasses.replace(engine._adapters, make_hotkey_listener=make)
        engine.start_fn_listener()
        assert make.call_args.kwargs["trigger"] == 61

    def test_min_speech_s_rewires_streaming_without_restart(self, engine, mocker):
        """A streaming-parameter change re-configures the live audio engine."""
        spy = mocker.spy(engine._audio_engine, "configure_streaming")
        engine.update_config({"min_speech_s": 1.5})
        assert spy.call_count == 1
        assert spy.call_args.kwargs["min_speech_s"] == 1.5

    def test_soft_gap_ms_rewires_streaming_without_restart(self, engine, mocker):
        """Changing soft_gap_ms re-configures the live audio engine the same
        way min_speech_s does above, without a manual Restart."""
        spy = mocker.spy(engine._audio_engine, "configure_streaming")
        engine.update_config({"soft_gap_ms": 500})
        assert spy.call_count == 1
        assert spy.call_args.kwargs["soft_gap_ms"] == 500

    def test_settings_survive_restart(self, engine, config_path):
        """Selecting settings then reloading from disk (a restart) keeps them.

        Guards the persistence path end-to-end: update_config -> save_config ->
        load_config returns the chosen values, not the defaults.
        """
        engine.update_config({"pause_ms": 800, "min_chunk_s": 0.6, "copy_to_clipboard": True})

        # Simulate a fresh process start: read the same file from scratch.
        reloaded = load_config(config_path)

        assert reloaded["pause_ms"] == 800
        assert reloaded["min_chunk_s"] == 0.6
        assert reloaded["copy_to_clipboard"] is True
        # And they differ from the shipped defaults, so this isn't a false pass.
        assert reloaded["pause_ms"] != DEFAULT_CONFIG["pause_ms"]


# ---------------------------------------------------------------------------
# DictationState
# ---------------------------------------------------------------------------


class TestDictationState:
    """Test DictationState initial state."""

    def test_initial_state(self):
        ds = DictationState()
        assert ds.is_recording is False
        assert ds.is_transcribing is False
        assert ds.model is None
        assert ds.model_loading is False
        assert ds.last_transcription is None
        assert ds.fn_listener_active is False
        assert ds.recording_process is None

    def test_config_defaults(self):
        ds = DictationState()
        for key in DEFAULT_CONFIG:
            assert key in ds.config


# ---------------------------------------------------------------------------
# Transcription worker FSM completion
# ---------------------------------------------------------------------------

import time

from whispy.core.state_machine import State


def _drive_to_transcribing(engine):
    """Move the FSM IDLE -> RECORDING -> TRANSCRIBING."""
    engine._state_machine.start_recording()
    engine._state_machine.stop_recording()
    assert engine._state_machine.current_state == State.TRANSCRIBING


def _run_worker_once(engine, mocker, transcription_side_effect):
    """Run the real worker through a single stop signal and stop it.

    transcription_side_effect is assigned to run_transcription (return value or
    an exception instance to raise).
    """
    mocker.patch("subprocess.Popen")  # silence the success sound
    if isinstance(transcription_side_effect, Exception):
        mocker.patch.object(engine, "run_transcription", side_effect=transcription_side_effect)
    else:
        mocker.patch.object(engine, "run_transcription", return_value=transcription_side_effect)

    engine.start_transcription_worker()
    try:
        engine.state.stop_event.set()
        # Wait for the worker to drive the FSM back to IDLE.
        deadline = time.time() + 2.0
        while engine._state_machine.current_state != State.IDLE and time.time() < deadline:
            time.sleep(0.02)
    finally:
        engine.stop_transcription_worker()


class TestTranscriptionWorkerFsm:
    """The worker must always return the FSM to IDLE after a stop signal."""

    def test_empty_transcription_completes_fsm(self, engine, mocker):
        _drive_to_transcribing(engine)
        _run_worker_once(engine, mocker, "")  # no usable text
        assert engine._state_machine.current_state == State.IDLE

    def test_transcription_exception_does_not_wedge_fsm(self, engine, mocker):
        _drive_to_transcribing(engine)
        _run_worker_once(engine, mocker, RuntimeError("boom"))
        # FSM recovered to IDLE and the worker survived (no thread crash).
        assert engine._state_machine.current_state == State.IDLE

    def test_successful_transcription_completes_fsm(self, engine, mocker):
        _drive_to_transcribing(engine)
        _run_worker_once(engine, mocker, "hello world")
        assert engine._state_machine.current_state == State.IDLE


# ---------------------------------------------------------------------------
# custom_vocabulary -> text-cleaning wiring
# ---------------------------------------------------------------------------


class TestCustomVocabularyWiring:
    """run_transcription hands the vocabulary to cleaning, never to the model."""

    def _prep(self, engine, mocker, tmp_path):
        """Point the recording path at a real file and stub the I/O side effects."""
        rec = tmp_path / "whispy.wav"
        rec.write_bytes(b"\x00" * 100)
        mocker.patch.object(type(engine._audio_engine), "recording_path", property(lambda self: str(rec)))
        engine.state.model = MagicMock()
        transcribe = mocker.patch.object(engine._audio_engine, "transcribe", return_value="hi")
        mocker.patch.object(engine._text_injector, "inject")
        mocker.patch.object(engine._audio_engine, "cleanup_audio_file")
        return transcribe

    def test_vocabulary_never_reaches_the_transcription_call(self, engine, mocker, tmp_path):
        """The transducer has no biasing channel; sending one would be a bug."""
        transcribe = self._prep(engine, mocker, tmp_path)
        engine.state.config["custom_vocabulary"] = ["Whispy", "Parakeet"]

        engine.run_transcription()

        kwargs = transcribe.call_args[1]
        for forbidden in ("initial_prompt", "hotwords", "vocabulary", "language"):
            assert forbidden not in kwargs, f"{forbidden} was forwarded to the model"

    def test_vocabulary_is_applied_during_cleaning(self, engine, mocker, tmp_path):
        transcribe = self._prep(engine, mocker, tmp_path)
        transcribe.return_value = "wispy is great"
        engine.state.config["custom_vocabulary"] = ["Whispy"]

        engine.run_transcription()

        assert engine.state.last_transcription == "Whispy is great"

    def test_empty_vocabulary_leaves_text_alone(self, engine, mocker, tmp_path):
        transcribe = self._prep(engine, mocker, tmp_path)
        transcribe.return_value = "wispy is great"
        engine.state.config["custom_vocabulary"] = []

        engine.run_transcription()

        assert engine.state.last_transcription == "wispy is great"


# ---------------------------------------------------------------------------
# copy_to_clipboard default
# ---------------------------------------------------------------------------


class TestClipboardDefault:
    """The TextInjector fallback must match DEFAULT_CONFIG (False)."""

    def test_injector_default_is_false_when_key_absent(self, config_path):
        from whispy.core.engine import Engine

        ds = DictationState()
        ds.config.pop("copy_to_clipboard", None)  # simulate a config missing the key
        eng = Engine(ds, config_path)
        assert eng._text_injector._copy_to_clipboard is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stray trigger release does not start transcription (fix-capture-thread-races)
# ---------------------------------------------------------------------------


class TestTriggerReleaseGating:
    """_handle_trigger_release_work only wakes the worker on a real stop."""

    def test_release_while_recording_sets_stop_event(self, engine):
        engine.state.stop_event.clear()
        engine._state_machine.start_recording()  # enter RECORDING
        engine._handle_trigger_release_work()
        assert engine.state.stop_event.is_set()

    def test_stray_release_does_not_set_stop_event(self, engine):
        # No active recording (FSM IDLE): a release must be a no-op so the
        # worker never transcribes a stale/missing file.
        engine.state.stop_event.clear()
        assert engine._state_machine.current_state == State.IDLE
        engine._handle_trigger_release_work()
        assert not engine.state.stop_event.is_set()


# ---------------------------------------------------------------------------
# Trigger callback handoff to a dedicated worker thread (fix-trigger-thread-blocking)
# ---------------------------------------------------------------------------


class TestTriggerCallbackHandoff:
    """The hardware-callback closures only enqueue; the worker does the real work."""

    def _capture_callbacks(self, engine, mocker):
        """Wire a fake hotkey listener and return the (press, release) closures
        the engine handed to it, without starting the trigger worker."""
        import dataclasses

        make = mocker.MagicMock(return_value=mocker.MagicMock(active=True))
        engine._adapters = dataclasses.replace(engine._adapters, make_hotkey_listener=make)
        engine.start_fn_listener()
        kwargs = make.call_args.kwargs
        return kwargs["on_trigger_press"], kwargs["on_trigger_release"]

    def test_press_callback_returns_without_blocking(self, engine, mocker):
        # A mock that would block forever if the callback called it directly.
        start_recording = mocker.patch.object(engine, "start_recording")
        press_cb, _ = self._capture_callbacks(engine, mocker)

        press_cb()  # the trigger worker is not running: this must not block or dispatch

        start_recording.assert_not_called()
        assert engine._trigger_queue.get(timeout=1.0) == "press"

    def test_release_callback_returns_without_blocking(self, engine, mocker):
        stop_recording = mocker.patch.object(engine, "stop_recording", side_effect=AssertionError("must not be called"))
        _, release_cb = self._capture_callbacks(engine, mocker)

        release_cb()

        stop_recording.assert_not_called()
        assert engine._trigger_queue.get(timeout=1.0) == "release"

    def test_press_then_release_processed_in_order(self, engine, mocker):
        order = []
        mocker.patch.object(engine, "_notify_fn_pressed")
        mocker.patch.object(engine._notifier, "recording_started")
        mocker.patch.object(engine, "_notify_fn_released")
        mocker.patch.object(engine, "start_recording", side_effect=lambda: order.append("start_recording"))
        mocker.patch.object(engine, "stop_recording", side_effect=lambda: order.append("stop_recording") or False)

        engine._trigger_queue.put("press")
        engine._trigger_queue.put("release")
        engine.start_trigger_worker()
        try:
            engine._trigger_queue.join()
        finally:
            engine.stop_trigger_worker()

        assert order == ["start_recording", "stop_recording"]

    def test_worker_preserves_press_call_order(self, engine, mocker):
        order = []
        mocker.patch.object(engine, "_notify_fn_pressed", side_effect=lambda: order.append("notify_pressed"))
        mocker.patch.object(engine._notifier, "recording_started", side_effect=lambda: order.append("sound"))
        mocker.patch.object(engine, "start_recording", side_effect=lambda: order.append("start") or True)

        engine._handle_trigger_press_work()

        assert order == ["notify_pressed", "sound", "start"]

    def test_worker_preserves_release_call_order(self, engine, mocker):
        order = []
        mocker.patch.object(engine, "_notify_fn_released", side_effect=lambda: order.append("notify_released"))
        mocker.patch.object(engine, "stop_recording", side_effect=lambda: order.append("stop") or True)
        engine.state.stop_event.clear()

        engine._handle_trigger_release_work()

        assert order == ["notify_released", "stop"]
        assert engine.state.stop_event.is_set()


# ---------------------------------------------------------------------------
# Model-load failure is surfaced (fix-capture-thread-races)
# ---------------------------------------------------------------------------


class TestModelLoadFailureSurfaced:
    """A failed model load fires the model-load-failed callback, not silence."""

    def test_failure_invokes_callback_and_clears_model(self, engine, mocker):
        from whispy.core import engine as engine_module

        mocker.patch.object(engine_module, "_load_model", side_effect=RuntimeError("no model"))
        mocker.patch.object(engine_module.time, "sleep")  # skip the retry backoff

        fired = threading.Event()
        messages: list[str] = []
        engine.on_model_load_failed(lambda msg: (messages.append(msg), fired.set()))

        engine_module.load_model_async(engine)
        assert fired.wait(timeout=3.0)
        assert engine.state.model is None
        assert engine.state.model_loading is False
        assert "no model" in messages[0]


# ---------------------------------------------------------------------------
# Capture-stream open failure is surfaced (refresh-audio-devices-before-capture)
# ---------------------------------------------------------------------------


class TestCaptureFailureSurfaced:
    """start_recording() fires on_capture_failed when the audio layer could not
    open a capture stream, and stays silent when capture is healthy."""

    def test_capture_failure_invokes_callback(self, engine, mocker):
        mocker.patch.object(engine._audio_engine, "start", return_value=True)
        mocker.patch.object(
            type(engine._audio_engine),
            "capture_failed",
            new_callable=mocker.PropertyMock,
            return_value="Internal PortAudio error [PaErrorCode -9986]",
        )
        messages: list[str] = []
        engine.on_capture_failed(messages.append)
        assert engine.start_recording() is True
        assert len(messages) == 1
        assert "-9986" in messages[0]

    def test_no_callback_when_capture_healthy(self, engine, mocker):
        mocker.patch.object(engine._audio_engine, "start", return_value=True)
        mocker.patch.object(
            type(engine._audio_engine),
            "capture_failed",
            new_callable=mocker.PropertyMock,
            return_value=None,
        )
        messages: list[str] = []
        engine.on_capture_failed(messages.append)
        assert engine.start_recording() is True
        assert messages == []

    def test_callback_exception_does_not_break_start(self, engine, mocker):
        mocker.patch.object(engine._audio_engine, "start", return_value=True)
        mocker.patch.object(
            type(engine._audio_engine),
            "capture_failed",
            new_callable=mocker.PropertyMock,
            return_value="no device",
        )

        def bad_cb(_msg):
            raise ValueError("oops")

        engine.on_capture_failed(bad_cb)
        assert engine.start_recording() is True


class TestInputUnheardSurfaced:
    """stop_recording() warns -- failure sound plus callback naming the device --
    when the recording only caught the noise floor, and stays quiet otherwise."""

    def _stop_with(self, engine, mocker, unheard: str | None):
        mocker.patch.object(engine._audio_engine, "stop", return_value=True)
        mocker.patch.object(
            type(engine._audio_engine),
            "unheard_input",
            new_callable=mocker.PropertyMock,
            return_value=unheard,
        )
        sound = mocker.patch.object(engine._notifier, "input_unheard")
        messages: list[str] = []
        engine.on_input_unheard(messages.append)
        assert engine.stop_recording() is True
        return sound, messages

    def test_unheard_recording_plays_failure_sound_and_names_device(self, engine, mocker):
        sound, messages = self._stop_with(engine, mocker, "Micro MacBook Pro")
        sound.assert_called_once()
        assert len(messages) == 1
        assert "Micro MacBook Pro" in messages[0]

    def test_heard_recording_stays_quiet(self, engine, mocker):
        sound, messages = self._stop_with(engine, mocker, None)
        sound.assert_not_called()
        assert messages == []


# ---------------------------------------------------------------------------
# Explicitly-denied startup permissions are surfaced (v1 blocker #2)
# ---------------------------------------------------------------------------


class TestPermissionMissingSurfaced:
    """engine.start() fires on_permission_missing for explicit denials only."""

    def _start_with_probe_results(self, engine, mocker, mic, inputmon, ax, auto):
        from types import SimpleNamespace

        from whispy.core import engine as engine_module

        mocker.patch.object(engine, "_adapters", SimpleNamespace(name="macos"))
        mocker.patch.object(engine, "start_fn_listener")
        mocker.patch.object(engine, "start_transcription_worker")
        mocker.patch.object(engine, "start_chunk_worker")
        mocker.patch.object(engine_module, "load_model_async")
        mocker.patch("whispy.platform.macos.permissions.ensure_microphone_access", return_value=mic)
        mocker.patch(
            "whispy.platform.macos.permissions.ensure_input_monitoring_access",
            return_value=inputmon,
        )
        mocker.patch("whispy.platform.macos.permissions.ensure_accessibility_access", return_value=ax)
        mocker.patch("whispy.platform.macos.permissions.ensure_automation_access", return_value=auto)

        fired: list[tuple[str, str]] = []
        engine.on_permission_missing(lambda kind, msg: fired.append((kind, msg)))
        engine.start()
        return fired

    def test_explicit_denials_fire_with_kind_and_guidance(self, engine, mocker):
        fired = self._start_with_probe_results(engine, mocker, mic=False, inputmon=False, ax=True, auto=True)
        assert [kind for kind, _ in fired] == ["microphone", "input_monitoring"]
        assert "System Settings" in fired[0][1]

    def test_granted_and_undetermined_stay_silent(self, engine, mocker):
        # None = the system prompt is on screen; warning would be noise.
        fired = self._start_with_probe_results(engine, mocker, mic=True, inputmon=None, ax=None, auto=True)
        assert fired == []


# ---------------------------------------------------------------------------
# run_transcription captures the per-recording path (isolation)
# ---------------------------------------------------------------------------


class TestRunTranscriptionPath:
    """Transcription uses the audio engine's current recording path."""

    def test_transcribes_the_recording_path(self, engine, mocker, tmp_path):
        wav = tmp_path / "rec-A.wav"
        wav.write_bytes(b"\x00" * 6000)
        mocker.patch.object(type(engine._audio_engine), "recording_path", property(lambda self: str(wav)))
        engine.state.model = MagicMock()
        transcribe = mocker.patch.object(engine._audio_engine, "transcribe", return_value="hi")
        mocker.patch.object(engine._text_injector, "inject")

        engine.run_transcription()
        assert transcribe.call_args[1]["audio_path"] == str(wav)


# ---------------------------------------------------------------------------
# run_transcription always deletes the recorded WAV (privacy)
# ---------------------------------------------------------------------------


class TestRunTranscriptionCleanup:
    """The recorded WAV must be removed no matter how transcription ends."""

    def _prep(self, engine, mocker, tmp_path):
        wav = tmp_path / "rec.wav"
        wav.write_bytes(b"\x00" * 6000)
        mocker.patch.object(type(engine._audio_engine), "recording_path", property(lambda self: str(wav)))
        engine.state.model = MagicMock()
        mocker.patch.object(engine._text_injector, "inject")
        return wav

    def test_deletes_wav_when_transcribe_returns_none(self, engine, mocker, tmp_path):
        wav = self._prep(engine, mocker, tmp_path)
        mocker.patch.object(engine._audio_engine, "transcribe", return_value=None)

        engine.run_transcription()

        assert not wav.exists()

    def test_deletes_wav_when_transcribe_returns_empty_string(self, engine, mocker, tmp_path):
        wav = self._prep(engine, mocker, tmp_path)
        mocker.patch.object(engine._audio_engine, "transcribe", return_value="")

        engine.run_transcription()

        assert not wav.exists()

    def test_deletes_wav_when_transcribe_raises(self, engine, mocker, tmp_path):
        wav = self._prep(engine, mocker, tmp_path)
        mocker.patch.object(engine._audio_engine, "transcribe", side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            engine.run_transcription()

        assert not wav.exists()

    def test_deletes_wav_when_model_not_loaded(self, engine, mocker, tmp_path):
        wav = tmp_path / "rec.wav"
        wav.write_bytes(b"\x00" * 6000)
        mocker.patch.object(type(engine._audio_engine), "recording_path", property(lambda self: str(wav)))
        engine.state.model = None

        engine.run_transcription()

        assert not wav.exists()


# ---------------------------------------------------------------------------
# Streaming / incremental transcription (chunk pipeline + FSM-1)
# ---------------------------------------------------------------------------


def _make_streaming_engine(config_path, mocker):
    """Engine with streaming enabled, a loaded model, and inject/transcribe spied."""
    from whispy.core.engine import Engine

    ds = DictationState()
    ds.config["streaming_enabled"] = True
    eng = Engine(ds, config_path)
    eng.state.model = MagicMock()  # non-None so chunks transcribe
    return eng


def _chunk_file(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"\x00" * 6000)
    return str(p)


class TestStreamingChunkPipeline:
    def test_chunks_accumulate_without_mid_recording_injection(self, config_path, mocker, tmp_path):
        # Chunks transcribed during recording are buffered, never typed mid-
        # recording (that would steal focus). The FSM worker types once on release.
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["alpha", "beta"])
        inject = mocker.patch.object(eng._text_injector, "inject")

        for n in ("a.wav", "b.wav"):
            eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, n), SENTENCE)

        inject.assert_not_called()
        # Each chunk's text carries its own leading separator now; the second
        # chunk was preceded by a sentence-length pause, so it gets " ".
        assert eng._chunk_texts == ["alpha", " beta"]

    def test_chunks_transcribed_independently(self, config_path, mocker, tmp_path):
        # No conditioning argument is passed to achieve independence: the
        # transducer carries no cross-call decoder context by construction.
        # Each call therefore differs only in the audio path.
        eng = _make_streaming_engine(config_path, mocker)
        eng.state.config["custom_vocabulary"] = ["Whispy"]
        transcribe = mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["one", "two"])
        mocker.patch.object(eng._text_injector, "inject")

        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "b.wav"), SENTENCE)

        assert len(transcribe.call_args_list) == 2
        for call in transcribe.call_args_list:
            for forbidden in ("initial_prompt", "condition_on_previous_text", "hotwords", "language"):
                assert forbidden not in call.kwargs
        # The only difference between the two calls is which chunk they read.
        paths = [c.kwargs["audio_path"] for c in transcribe.call_args_list]
        assert paths[0] != paths[1]

    def test_empty_chunk_injects_nothing(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", return_value=None)
        inject = mocker.patch.object(eng._text_injector, "inject")
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
        inject.assert_not_called()

    def test_worker_survives_chunk_error_and_drains(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=RuntimeError("boom"))
        mocker.patch.object(eng._text_injector, "inject")
        eng.start_chunk_worker()
        try:
            eng._enqueue_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
            eng._chunk_queue.join()  # would hang if the worker died on the error
        finally:
            eng.stop_chunk_worker()

    def test_mid_recording_chunks_do_not_set_is_transcribing(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", return_value="hi")
        mocker.patch.object(eng._text_injector, "inject")
        eng._state_machine.start_recording()  # RECORDING
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
        assert eng.state.is_transcribing is False
        assert eng._state_machine.is_recording is True

    def test_tail_flush_drains_and_returns_idle(self, config_path, mocker, tmp_path):
        import time

        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["bonjour", "le monde"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        eng.start_chunk_worker()
        eng.start_transcription_worker()
        try:
            eng._on_fsm_recording(None)  # reset per-recording accumulators
            eng._state_machine.start_recording()
            eng._enqueue_chunk(_chunk_file(tmp_path, "c1.wav"), SENTENCE)
            eng._state_machine.stop_recording()  # -> TRANSCRIBING
            eng._enqueue_chunk(_chunk_file(tmp_path, "tail.wav"), SENTENCE)  # tail chunk (always SENTENCE)
            eng.state.stop_event.set()
            deadline = time.time() + 5.0
            while eng._state_machine.current_state.name != "IDLE" and time.time() < deadline:
                time.sleep(0.02)
            assert eng._state_machine.current_state.name == "IDLE"
            # Assembled once on release — not per chunk.
            inject.assert_called_once_with("bonjour le monde")
        finally:
            eng.stop_transcription_worker()
            eng.stop_chunk_worker()


class TestChunkStateLocking:
    """`_chunk_texts`/`_chunk_any_text` are guarded by `DictationState.lock`."""

    def test_chunk_worker_append_is_lock_guarded(self, engine, mocker, tmp_path):
        lock = mocker.MagicMock()
        engine.state.lock = lock
        engine.state.model = mocker.MagicMock()
        mocker.patch.object(engine._audio_engine, "transcribe", return_value="hello")

        engine._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)

        lock.__enter__.assert_called()
        lock.__exit__.assert_called()
        assert engine._chunk_texts == ["hello"]

    def test_recording_entry_reset_is_lock_guarded(self, engine, mocker):
        lock = mocker.MagicMock()
        engine.state.lock = lock
        engine._chunk_texts = ["stale"]
        engine._chunk_any_text = True

        engine._on_fsm_recording(None)

        lock.__enter__.assert_called()
        lock.__exit__.assert_called()
        assert engine._chunk_texts == []
        assert engine._chunk_any_text is False

    def test_force_recover_reset_is_lock_guarded(self, engine, mocker):
        lock = mocker.MagicMock()
        engine.state.lock = lock
        engine._chunk_texts = ["stale"]
        engine._chunk_any_text = True

        engine._force_recover()

        lock.__enter__.assert_called()
        lock.__exit__.assert_called()
        assert engine._chunk_texts == []
        assert engine._chunk_any_text is False

    def test_transcription_worker_read_is_lock_guarded(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", return_value="hi")
        mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")
        lock = mocker.MagicMock()
        eng.state.lock = lock

        eng.start_chunk_worker()
        eng.start_transcription_worker()
        try:
            eng._state_machine.start_recording()
            eng._enqueue_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
            eng._chunk_queue.join()
            eng._state_machine.stop_recording()  # -> TRANSCRIBING
            eng.state.stop_event.set()
            deadline = time.time() + 5.0
            while eng._state_machine.current_state.name != "IDLE" and time.time() < deadline:
                time.sleep(0.02)
            assert eng._state_machine.current_state.name == "IDLE"
        finally:
            eng.stop_transcription_worker()
            eng.stop_chunk_worker()

        # Both the recording-entry reset and the release-time read acquired
        # the (mocked) lock rather than touching the fields unguarded.
        assert lock.__enter__.call_count >= 2
        assert lock.__exit__.call_count == lock.__enter__.call_count

    def test_concurrent_chunk_appends_and_read_are_consistent(self, engine, mocker, tmp_path):
        # Regression guard: real threads hammering the append/read paths must
        # never raise and must always see a consistent list length — the
        # unlocked race this requirement closes.
        engine.state.model = mocker.MagicMock()
        mocker.patch.object(engine._audio_engine, "transcribe", return_value="x")

        errors: list[Exception] = []
        n = 50

        def append_many():
            try:
                for i in range(n):
                    path = _chunk_file(tmp_path, f"c{i}.wav")
                    engine._transcribe_and_inject_chunk(path, SENTENCE)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        def read_many():
            try:
                for _ in range(n):
                    with engine.state.lock:
                        list(engine._chunk_texts)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=append_many), threading.Thread(target=read_many)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert errors == []
        with engine.state.lock:
            assert len(engine._chunk_texts) == n


class TestStopAndWaitForTranscription:
    """Engine.stop_and_wait_for_transcription: the single sync-stop code path."""

    def test_streaming_mode_returns_assembled_text(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["bonjour", "le monde"])
        mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        eng.start_chunk_worker()
        eng.start_transcription_worker()
        try:
            eng._on_fsm_recording(None)
            eng._state_machine.start_recording()
            eng._enqueue_chunk(_chunk_file(tmp_path, "c1.wav"), SENTENCE)
            eng._chunk_queue.join()
            eng._enqueue_chunk(_chunk_file(tmp_path, "c2.wav"), SENTENCE)
            eng._chunk_queue.join()

            text = eng.stop_and_wait_for_transcription(timeout=5.0)

            assert text == "bonjour le monde"
            assert eng._state_machine.current_state.name == "IDLE"
        finally:
            eng.stop_transcription_worker()
            eng.stop_chunk_worker()

    def test_noop_when_not_recording_returns_none_immediately(self, engine):
        engine.state.stop_event.clear()
        assert engine._state_machine.current_state == State.IDLE

        result = engine.stop_and_wait_for_transcription(timeout=0.5)

        assert result is None
        assert not engine.state.stop_event.is_set()

    def test_returns_after_timeout_when_worker_stalled(self, engine):
        # RECORDING with no transcription worker running: stop_event is set
        # but never consumed, so the done event is never signaled.
        engine._state_machine.start_recording()

        t0 = time.monotonic()
        engine.stop_and_wait_for_transcription(timeout=0.2)
        elapsed = time.monotonic() - t0

        assert elapsed < 2.0  # bounded — did not hang waiting forever


class TestStreamFileSeam:
    """engine.stream_file: deterministic streaming seam (no mic, no inject)."""

    def _wav(self, tmp_path, name="a.wav"):
        import wave

        p = tmp_path / name
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00" * 32000)
        return str(p)

    def test_returns_ordered_chunk_texts(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        wav = self._wav(tmp_path)
        mocker.patch.object(eng._audio_engine, "segment_pcm", return_value=["c1", "c2"])
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["un", "deux"])
        cleanup = mocker.patch.object(eng._audio_engine, "cleanup_audio_file")
        assert eng.stream_file(wav) == ["un", "deux"]
        # Each chunk file is cleaned up after transcription.
        assert cleanup.call_count == 2

    def _speech_wav(self, tmp_path, name="speech.wav"):
        import wave

        import numpy as np

        p = tmp_path / name
        pcm = np.random.RandomState(0).randint(-9000, 9000, 16000).astype(np.int16).tobytes()
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)
        return str(p)

    def test_real_segmentation_path(self, config_path, mocker, tmp_path):
        # Exercise the REAL segment_pcm (not mocked) so a kwarg mismatch between
        # stream_file and segment_pcm is caught — the bug that crashed /stream-file.
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", return_value="chunk text")
        result = eng.stream_file(self._speech_wav(tmp_path))
        assert result is not None
        assert all(isinstance(t, str) for t in result)

    def test_none_when_model_unloaded(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        eng.state.model = None
        assert eng.stream_file(self._wav(tmp_path)) is None

    def test_none_when_file_missing(self, config_path, mocker):
        eng = _make_streaming_engine(config_path, mocker)
        assert eng.stream_file("/nope/missing.wav") is None


class TestLiveTypingWithoutStreaming:
    """`streaming_enabled: false` silently disables live typing -- say so."""

    def test_the_contradiction_is_reported(self, config_path, caplog):
        from whispy.core.engine import Engine

        ds = DictationState()
        ds.config["streaming_enabled"] = False
        ds.config["type_while_speaking"] = True

        with caplog.at_level(logging.WARNING, logger="whispy.core.engine"):
            Engine(ds, config_path)

        assert "type_while_speaking" in caplog.text
        assert "streaming_enabled" in caplog.text

    def test_nothing_is_reported_when_the_two_agree(self, config_path, caplog):
        from whispy.core.engine import Engine

        ds = DictationState()
        ds.config["streaming_enabled"] = True
        ds.config["type_while_speaking"] = True

        with caplog.at_level(logging.WARNING, logger="whispy.core.engine"):
            Engine(ds, config_path)

        assert "type_while_speaking is on but" not in caplog.text

    def test_live_typing_off_with_streaming_off_is_not_a_contradiction(self, config_path, caplog):
        from whispy.core.engine import Engine

        ds = DictationState()
        ds.config["streaming_enabled"] = False
        ds.config["type_while_speaking"] = False

        with caplog.at_level(logging.WARNING, logger="whispy.core.engine"):
            Engine(ds, config_path)

        assert "type_while_speaking is on but" not in caplog.text


class TestStreamingRuntimeToggle:
    """update_config re-wires streaming and the chunk worker at runtime."""

    def test_enable_wires_audio_and_starts_worker(self, config_path, mocker):
        from whispy.core.engine import Engine

        ds = DictationState()
        ds.config["streaming_enabled"] = False
        eng = Engine(ds, config_path)
        assert eng._streaming is False
        eng._transcription_running = True  # simulate a started engine
        start_spy = mocker.patch.object(eng, "start_chunk_worker")
        stop_spy = mocker.patch.object(eng, "stop_chunk_worker")

        eng.update_config({"streaming_enabled": True})

        assert eng._streaming is True
        assert eng._audio_engine._streaming is True
        start_spy.assert_called_once()
        stop_spy.assert_not_called()

    def test_disable_stops_worker(self, config_path, mocker):
        from whispy.core.engine import Engine

        ds = DictationState()
        ds.config["streaming_enabled"] = True
        eng = Engine(ds, config_path)
        assert eng._streaming is True
        eng._transcription_running = True
        start_spy = mocker.patch.object(eng, "start_chunk_worker")
        stop_spy = mocker.patch.object(eng, "stop_chunk_worker")

        eng.update_config({"streaming_enabled": False})

        assert eng._streaming is False
        assert eng._audio_engine._streaming is False
        stop_spy.assert_called_once()
        start_spy.assert_not_called()

    def test_toggle_before_start_does_not_touch_worker(self, config_path, mocker):
        from whispy.core.engine import Engine

        ds = DictationState()
        eng = Engine(ds, config_path)  # not started: _transcription_running is False
        start_spy = mocker.patch.object(eng, "start_chunk_worker")
        stop_spy = mocker.patch.object(eng, "stop_chunk_worker")

        eng.update_config({"streaming_enabled": True})

        assert eng._streaming is True
        start_spy.assert_not_called()
        stop_spy.assert_not_called()


class TestChunkDrainTimeout:
    """_drain_chunk_queue bounds the on-release wait so a stalled chunk can't wedge TRANSCRIBING."""

    def test_drain_returns_true_when_empty(self, engine):
        assert engine._drain_chunk_queue(0.5) is True

    def test_drain_times_out_on_unfinished_chunk(self, engine):
        import time

        engine._chunk_queue.put("stuck")  # never task_done() — simulates a stalled chunk
        t0 = time.monotonic()
        assert engine._drain_chunk_queue(0.2) is False
        assert time.monotonic() - t0 < 2.0  # returned promptly, did not block forever

    def test_drain_returns_true_after_task_done(self, engine):
        engine._chunk_queue.put("x")
        engine._chunk_queue.task_done()
        assert engine._drain_chunk_queue(0.5) is True


class TestWatchdogRecovery:
    """The FSM watchdog force-recovers a wedged RECORDING/TRANSCRIBING to IDLE."""

    def test_recording_limit_stops_gracefully_and_preserves_text(self, engine):
        """Reaching RECORDING_MAX_S hands off to the ordinary stop path.

        The old behavior force-recovered, and _force_recover clears _chunk_texts.
        Under push-to-talk that was nearly unreachable; a toggle-mode dictation
        can legitimately run five minutes, and discarding already-transcribed
        speech is never the desired outcome.
        """
        import time

        import whispy.core.engine as eng_mod

        messages = []
        engine.on_recording_limit_reached(messages.append)
        engine._state_machine.start_recording()
        assert engine._state_machine.is_recording
        with engine.state.lock:
            engine._chunk_texts = ["bonjour"]
        # Pretend recording started long before the RECORDING backstop.
        engine._recording_since = time.monotonic() - (eng_mod.RECORDING_MAX_S + 1)

        engine._watchdog_tick()

        # Handed to the transcription worker, not force-recovered.
        assert engine._state_machine.is_transcribing
        assert engine.state.stop_event.is_set()
        assert engine._deliver_to_clipboard is True
        # The transcript survives for the worker to assemble.
        assert engine._chunk_texts == ["bonjour"]
        assert len(messages) == 1
        assert "clipboard" in messages[0]

    def test_failed_graceful_stop_falls_back_to_forced_recovery(self, engine, mocker):
        """The watchdog exists to break a wedged FSM: if the graceful stop cannot
        transition RECORDING -> TRANSCRIBING, forced recovery still runs."""
        import time

        import whispy.core.engine as eng_mod

        mocker.patch.object(engine, "stop_recording", side_effect=RuntimeError("boom"))
        engine._state_machine.start_recording()
        engine._recording_since = time.monotonic() - (eng_mod.RECORDING_MAX_S + 1)

        engine._watchdog_tick()

        assert engine._state_machine.is_idle
        assert engine._deliver_to_clipboard is False

    def test_transcribing_watchdog_recovers_to_idle(self, engine):
        import time

        import whispy.core.engine as eng_mod

        engine._state_machine.start_recording()
        engine._state_machine.stop_recording()
        assert engine._state_machine.is_transcribing
        engine._transcribing_since = time.monotonic() - (eng_mod.TRANSCRIBING_MAX_S + 1)
        engine._watchdog_tick()
        assert engine._state_machine.is_idle

    def test_normal_dwell_is_not_recovered(self, engine):
        import time

        engine._state_machine.start_recording()
        engine._recording_since = time.monotonic()  # just entered — well within timeout
        engine._watchdog_tick()
        assert engine._state_machine.is_recording


class TestInjectWaitsForTriggerRelease:
    """Typing while the push-to-talk key is held merges the held modifier
    into every injected character (e.g. Right Option -> Option-layer glyphs).
    Both inject paths must wait (bounded) for release first."""

    def test_wait_returns_immediately_when_not_pressed(self, engine):
        start = time.monotonic()
        engine._wait_trigger_released(timeout=5.0)
        assert time.monotonic() - start < 0.5

    def test_wait_blocks_until_release(self, engine):
        engine._fn_pressed = True
        threading.Timer(0.15, lambda: setattr(engine, "_fn_pressed", False)).start()
        start = time.monotonic()
        engine._wait_trigger_released(timeout=5.0)
        elapsed = time.monotonic() - start
        assert 0.1 <= elapsed < 2.0

    def test_wait_times_out_on_stuck_flag(self, engine):
        engine._fn_pressed = True
        start = time.monotonic()
        engine._wait_trigger_released(timeout=0.2)
        assert time.monotonic() - start < 2.0  # bounded, never wedges the worker

    def test_run_transcription_waits_before_inject(self, engine, mocker, tmp_path):
        """The whole-file inject path calls the release gate before typing."""
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"fake")
        engine._audio_engine._recording_path = str(wav)
        engine.state.model = mocker.MagicMock()
        mocker.patch.object(engine._audio_engine, "transcribe", return_value="hello")
        inject_mock = mocker.patch.object(engine._text_injector, "inject")
        wait_mock = mocker.patch.object(engine, "_wait_trigger_released")

        engine.run_transcription()

        wait_mock.assert_called_once()
        inject_mock.assert_called_once_with("hello")

    def test_streaming_assembly_waits_before_inject(self):
        """The streaming (assembled chunks) inject path is also gated."""
        import inspect

        from whispy.core.engine import Engine

        src = inspect.getsource(Engine.start_transcription_worker)
        # Delivery now goes through _deliver(), which chooses inject vs clipboard.
        inject_idx = src.index("_deliver(assembled)")
        assembled_idx = src.index("assembled = ")
        assert "_wait_trigger_released()" in src[assembled_idx:inject_idx]


class TestNoDoubleInjectionOnRapidRepress:
    """Rapid re-press while the previous transcription is in flight: both
    recordings' chunks can land in one buffer and the second stop_event used
    to re-inject the identical assembled text (buffer was only cleared at
    recording start, never on consumption)."""

    def test_second_stop_event_does_not_reinject(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["test 1 2", "3"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        eng.start_chunk_worker()
        eng.start_transcription_worker()
        try:
            # Recording n and a quick re-press n+1: chunks from both end up
            # in the same buffer before the worker consumes it.
            eng._on_fsm_recording(None)
            eng._state_machine.start_recording()
            eng._enqueue_chunk(_chunk_file(tmp_path, "c1.wav"), SENTENCE)
            eng._chunk_queue.join()
            eng._enqueue_chunk(_chunk_file(tmp_path, "c2.wav"), SENTENCE)
            eng._chunk_queue.join()

            # Stop n: worker consumes and injects the assembled buffer.
            assert eng.stop_and_wait_for_transcription(timeout=5.0) == "test 1 2 3"
            inject.assert_called_once_with("test 1 2 3")

            # Stop n+1 arrives with no new speech: FSM cycles again but the
            # buffer was consumed — nothing to inject a second time.
            eng._state_machine.start_recording()
            eng._transcription_done_event.clear()
            eng.state.stop_event.set()
            eng._state_machine.stop_recording()
            assert eng._transcription_done_event.wait(timeout=5.0)

            inject.assert_called_once()  # still exactly one injection
        finally:
            eng.stop_transcription_worker()
            eng.stop_chunk_worker()


class TestTriggerModeDispatch:
    """Toggle mode routes press/release differently from hold mode, in the one
    cross-platform seam (the trigger worker) rather than in either platform
    listener, so macOS and Linux cannot drift apart."""

    def test_hold_mode_press_starts_and_release_stops(self, engine, mocker):
        press = mocker.patch.object(engine, "_handle_trigger_press_work")
        release = mocker.patch.object(engine, "_handle_trigger_release_work")

        assert engine._trigger_mode == "hold"
        engine._handle_trigger_press_signal()
        press.assert_called_once()
        release.assert_not_called()

        engine._handle_trigger_release_signal()
        release.assert_called_once()

    def test_toggle_press_starts_when_idle(self, engine, mocker):
        engine.update_config({"trigger_mode": "toggle"})
        press = mocker.patch.object(engine, "_handle_trigger_press_work")
        release = mocker.patch.object(engine, "_handle_trigger_release_work")

        engine._handle_trigger_press_signal()

        press.assert_called_once()
        release.assert_not_called()

    def test_toggle_second_press_stops(self, engine, mocker):
        engine.update_config({"trigger_mode": "toggle"})
        engine._state_machine.start_recording()
        press = mocker.patch.object(engine, "_handle_trigger_press_work")
        stop = mocker.patch.object(engine, "_stop_and_signal")

        engine._handle_trigger_press_signal()

        stop.assert_called_once()
        press.assert_not_called()

    def test_toggle_stop_does_not_announce_a_release(self, engine, mocker):
        """Regression: the stopping press arrives with the keys physically down.

        Announcing a release there hides the waveform pill (the menu bar listens
        on that event) and, worse, clears the trigger-held flag while the
        combination is still held -- letting injection start with the modifiers
        down.
        """
        engine.update_config({"trigger_mode": "toggle"})
        engine._state_machine.start_recording()
        released = []
        engine.on_fn_released(lambda: released.append(1))
        mocker.patch.object(engine, "stop_recording", return_value=True)

        engine._handle_trigger_press_signal()

        assert released == []
        assert engine._fn_pressed is True

    def test_toggle_release_does_not_stop_recording(self, engine, mocker):
        engine.update_config({"trigger_mode": "toggle"})
        engine._state_machine.start_recording()
        release = mocker.patch.object(engine, "_handle_trigger_release_work")

        engine._handle_trigger_release_signal()

        release.assert_not_called()
        assert engine._state_machine.is_recording

    def test_mode_change_applies_without_a_restart(self, engine):
        assert engine._trigger_mode == "hold"
        engine.update_config({"trigger_mode": "toggle"})
        assert engine._trigger_mode == "toggle"
        engine.update_config({"trigger_mode": "hold"})
        assert engine._trigger_mode == "hold"


class TestToggleKeepsTriggerHeldFlagAccurate:
    """Regression guard for the trap in toggle mode: the release no longer stops
    recording, but it must still clear _fn_pressed. Left set, _wait_trigger_released
    would block every injection for its full timeout -- and because streaming
    injects almost immediately after the stopping press, a modifier still recorded
    as held is exactly what mangles the typed characters."""

    def test_release_clears_fn_pressed_in_toggle_mode(self, engine):
        engine.update_config({"trigger_mode": "toggle"})
        engine._notify_fn_pressed()
        assert engine._fn_pressed is True

        engine._handle_trigger_release_signal()

        assert engine._fn_pressed is False

    def test_toggle_release_does_not_fan_out_to_subscribers(self, engine):
        """Regression (found in live-drive): the pill vanished mid-dictation.

        In toggle mode the key is released seconds before the dictation ends, so
        the release must clear the flag WITHOUT announcing a release -- the menu
        bar hides the waveform on that event. The pill's lifecycle belongs to
        the recording, not to the key.
        """
        engine.update_config({"trigger_mode": "toggle"})
        engine._notify_fn_pressed()
        released = []
        engine.on_fn_released(lambda: released.append(1))

        engine._handle_trigger_release_signal()

        assert released == []
        assert engine._fn_pressed is False

    def test_hold_mode_release_still_fans_out(self, engine, mocker):
        """The hold path must keep announcing releases -- that is what puts the
        pill away when a press showed it but recording never started."""
        mocker.patch.object(engine, "stop_recording", return_value=False)
        released = []
        engine.on_fn_released(lambda: released.append(1))

        engine._handle_trigger_release_signal()

        assert released == [1]

    def test_wait_returns_immediately_after_a_toggle_release(self, engine):
        import time

        engine.update_config({"trigger_mode": "toggle"})
        engine._notify_fn_pressed()
        engine._handle_trigger_release_signal()

        t0 = time.monotonic()
        engine._wait_trigger_released()
        assert time.monotonic() - t0 < 1.0


class TestRecordingLimitDelivery:
    """At the recording limit the transcript is copied, not typed: after minutes
    of speech there is no basis for assuming the originally focused field still
    has focus."""

    def test_limit_flag_routes_delivery_to_the_clipboard(self, engine, mocker):
        copy = mocker.patch.object(engine._text_injector, "copy_only")
        inject = mocker.patch.object(engine._text_injector, "inject")
        engine._deliver_to_clipboard = True

        engine._deliver("bonjour")

        copy.assert_called_once_with("bonjour")
        inject.assert_not_called()

    def test_normal_delivery_injects(self, engine, mocker):
        copy = mocker.patch.object(engine._text_injector, "copy_only")
        inject = mocker.patch.object(engine._text_injector, "inject")

        engine._deliver("bonjour")

        inject.assert_called_once_with("bonjour")
        copy.assert_not_called()

    def test_flag_is_cleared_once_per_cycle_not_in_deliver(self):
        """A cycle that produced no text never reaches _deliver, so clearing the
        one-shot flag there would let it leak into the next dictation."""
        import inspect

        from whispy.core.engine import Engine

        src = inspect.getsource(Engine.start_transcription_worker)
        assert "self._deliver_to_clipboard = False" in src
        assert "self._deliver_to_clipboard = False" not in inspect.getsource(Engine._deliver)


# ---------------------------------------------------------------------------
# Type while speaking (toggle mode: chunks typed as they land)
# ---------------------------------------------------------------------------


def _make_toggle_streaming_engine(config_path, mocker, type_while_speaking=True):
    eng = _make_streaming_engine(config_path, mocker)
    eng.state.config["trigger_mode"] = "toggle"
    eng.state.config["type_while_speaking"] = type_while_speaking
    eng._trigger_mode = "toggle"
    return eng


class TestTypeWhileSpeakingSnapshot:
    """The live-typing decision is taken once per recording, at recording start."""

    def test_toggle_mode_with_key_on_is_live(self, config_path, mocker):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        eng._on_fsm_recording(None)
        assert eng._live_typing is True
        # Nothing delivered yet this recording, so the next chunk carries no prefix.
        assert eng._prev_boundary is None
        assert eng._pending_period is False

    def test_hold_mode_is_never_live(self, config_path, mocker):
        eng = _make_streaming_engine(config_path, mocker)
        eng.state.config["type_while_speaking"] = True
        eng._on_fsm_recording(None)
        assert eng._live_typing is False

    def test_toggle_mode_with_key_off_is_not_live(self, config_path, mocker):
        eng = _make_toggle_streaming_engine(config_path, mocker, type_while_speaking=False)
        eng._on_fsm_recording(None)
        assert eng._live_typing is False

    def test_force_recover_clears_live_flags(self, config_path, mocker):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        eng._on_fsm_recording(None)
        eng._prev_boundary = CONTINUATION
        eng._pending_period = True
        eng._force_recover()
        assert eng._live_typing is False
        assert eng._prev_boundary is None
        assert eng._pending_period is False


class TestTypeWhileSpeakingChunks:
    def test_chunks_are_typed_as_they_land_with_one_space_between(self, config_path, mocker, tmp_path):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["alpha", "beta"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        wait = mocker.patch.object(eng, "_wait_trigger_released")
        eng._on_fsm_recording(None)

        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "b.wav"), SENTENCE)

        assert [c.args[0] for c in inject.call_args_list] == ["alpha", " beta"]
        assert wait.call_count == 2  # release gate before every live inject
        # Accumulation is kept so last_transcription / the limit copy see
        # everything -- each entry already carries the separator its own
        # boundary called for, matching exactly what was typed live.
        assert eng._chunk_texts == ["alpha", " beta"]

    def test_empty_chunk_types_nothing_and_does_not_add_a_space(self, config_path, mocker, tmp_path):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=[None, "beta"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        eng._on_fsm_recording(None)

        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "b.wav"), SENTENCE)

        # The empty first chunk left nothing delivered, so "beta" is still the
        # first chunk to produce text and carries no prefix.
        inject.assert_called_once_with("beta")

    def test_hold_mode_still_accumulates_only(self, config_path, mocker, tmp_path):
        eng = _make_streaming_engine(config_path, mocker)
        eng.state.config["type_while_speaking"] = True  # inert in hold mode
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["alpha"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        eng._on_fsm_recording(None)

        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)

        inject.assert_not_called()
        assert eng._chunk_texts == ["alpha"]


class TestTypeWhileSpeakingStop:
    def _run_live_cycle(self, eng, tmp_path, texts, reasons=None):
        reasons = reasons or [SENTENCE] * len(texts)
        eng.start_chunk_worker()
        eng.start_transcription_worker()
        try:
            eng._on_fsm_recording(None)
            eng._state_machine.start_recording()
            for i, reason in enumerate(reasons):
                eng._enqueue_chunk(_chunk_file(tmp_path, f"c{i}.wav"), reason)
                eng._chunk_queue.join()
            return eng.stop_and_wait_for_transcription(timeout=5.0)
        finally:
            eng.stop_transcription_worker()
            eng.stop_chunk_worker()

    def test_stop_does_not_retype_the_assembled_text(self, config_path, mocker, tmp_path):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["bonjour", "le monde"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        text = self._run_live_cycle(eng, tmp_path, ["bonjour", "le monde"])

        assert text == "bonjour le monde"
        assert [c.args[0] for c in inject.call_args_list] == ["bonjour", " le monde"]
        assert eng.state.last_transcription == "bonjour le monde"
        assert eng._state_machine.current_state.name == "IDLE"
        assert eng._live_typing is False

    def test_limit_stop_still_copies_the_whole_transcript(self, config_path, mocker, tmp_path):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["bonjour", "le monde"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        copy = mocker.patch.object(eng._text_injector, "copy_only")
        mocker.patch.object(eng._notifier, "transcription_succeeded")
        eng._deliver_to_clipboard = True  # what _handle_recording_limit sets

        self._run_live_cycle(eng, tmp_path, ["bonjour", "le monde"])

        copy.assert_called_once_with("bonjour le monde")
        assert [c.args[0] for c in inject.call_args_list] == ["bonjour", " le monde"]
        assert eng._deliver_to_clipboard is False  # consumed once per cycle

    def test_key_off_in_toggle_mode_types_once_at_stop(self, config_path, mocker, tmp_path):
        eng = _make_toggle_streaming_engine(config_path, mocker, type_while_speaking=False)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["bonjour", "le monde"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        self._run_live_cycle(eng, tmp_path, ["bonjour", "le monde"])

        inject.assert_called_once_with("bonjour le monde")


class TestTypeWhileSpeakingRuntimeConfig:
    def test_mid_recording_flip_applies_to_the_next_recording(self, config_path, mocker, tmp_path):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["alpha", "beta", "gamma"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        eng._on_fsm_recording(None)

        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), SENTENCE)
        eng.update_config({"type_while_speaking": False})
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "b.wav"), SENTENCE)
        # Snapshot holds for the recording in progress.
        assert [c.args[0] for c in inject.call_args_list] == ["alpha", " beta"]

        eng._on_fsm_recording(None)  # next recording
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "c.wav"), SENTENCE)
        assert inject.call_count == 2  # gamma accumulated, not typed
        assert eng._chunk_texts == ["gamma"]

    def test_update_rewires_streaming_without_restarting_the_worker(self, config_path, mocker):
        eng = _make_toggle_streaming_engine(config_path, mocker)
        apply = mocker.patch.object(eng, "_apply_streaming_config")
        stop = mocker.patch.object(eng, "stop_chunk_worker")
        eng._transcription_running = True  # "engine started"
        eng._streaming = True
        start = mocker.patch.object(eng, "start_chunk_worker")

        eng.update_config({"type_while_speaking": False})

        apply.assert_called_once()
        stop.assert_not_called()
        start.assert_called_once()  # idempotent no-op when already running
        assert eng.state.config["type_while_speaking"] is False


# ---------------------------------------------------------------------------
# Continuation-aware join delivery (fix-dictation-text-fidelity, tasks 4.2-4.5)
# ---------------------------------------------------------------------------


class TestContinuationJoinDelivery:
    """Withheld periods, live-typed separators across a continuation boundary,
    and parity between the live and stop-time assembly paths."""

    def _run_cycle(self, eng, tmp_path, chunks):
        """Run one full recording through the real chunk-worker /
        transcription-worker pipeline. ``chunks`` is an ordered list of
        (text, reason) pairs the mocked model will yield, one per enqueued
        chunk. Returns the assembled text from stop_and_wait_for_transcription.
        """
        eng.start_chunk_worker()
        eng.start_transcription_worker()
        try:
            eng._on_fsm_recording(None)
            eng._state_machine.start_recording()
            for i, (_text, reason) in enumerate(chunks):
                eng._enqueue_chunk(_chunk_file(tmp_path, f"c{i}.wav"), reason)
                eng._chunk_queue.join()
            return eng.stop_and_wait_for_transcription(timeout=5.0)
        finally:
            eng.stop_transcription_worker()
            eng.stop_chunk_worker()

    def test_three_chunk_recording_restores_the_final_withheld_period(self, config_path, mocker, tmp_path):
        # 4.2: the last chunk's own trailing period is withheld at delivery
        # (its own boundary reason is a continuation cut) and restored once
        # the recording stops, since no further boundary follows it.
        eng = _make_toggle_streaming_engine(config_path, mocker)
        chunks = [("one", SENTENCE), ("two", CONTINUATION), ("three.", CONTINUATION)]
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=[t for t, _ in chunks])
        inject = mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        text = self._run_cycle(eng, tmp_path, chunks)

        # Typed live, in emission order, with the final period withheld until
        # the tail (a separate injection, since typing is append-only).
        assert [c.args[0] for c in inject.call_args_list] == ["one", " two", " three", "."]
        assert text == "one two three."

    def test_continuation_boundary_drops_the_period_and_lowers_the_next_capital(self, config_path, mocker, tmp_path):
        # 4.3: the live-typing path across a continuation boundary.
        eng = _make_toggle_streaming_engine(config_path, mocker)
        chunks = [("Des tickets.", CONTINUATION), ("Qui se baladent.", SENTENCE)]
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=[t for t, _ in chunks])
        inject = mocker.patch.object(eng._text_injector, "inject")
        mocker.patch.object(eng._notifier, "transcription_succeeded")

        text = self._run_cycle(eng, tmp_path, chunks)

        assert [c.args[0] for c in inject.call_args_list] == [
            "Des tickets",  # typed without its trailing period
            ", qui se baladent.",  # leading ", " and a lowered first letter
        ]
        assert text == "Des tickets, qui se baladent."

    def test_stop_time_assembly_matches_the_live_typed_concatenation(self, config_path, mocker, tmp_path):
        # 4.4: the same chunk sequence with type_while_speaking off must
        # assemble to exactly what the live path would have typed, so the two
        # paths cannot diverge.
        chunks = [("Des tickets.", CONTINUATION), ("Qui se baladent.", SENTENCE)]

        live_eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(live_eng._audio_engine, "transcribe", side_effect=[t for t, _ in chunks])
        live_inject = mocker.patch.object(live_eng._text_injector, "inject")
        mocker.patch.object(live_eng._notifier, "transcription_succeeded")
        live_text = self._run_cycle(live_eng, tmp_path, chunks)
        live_typed_concat = "".join(c.args[0] for c in live_inject.call_args_list)

        off_eng = _make_toggle_streaming_engine(config_path, mocker, type_while_speaking=False)
        mocker.patch.object(off_eng._audio_engine, "transcribe", side_effect=[t for t, _ in chunks])
        inject = mocker.patch.object(off_eng._text_injector, "inject")
        mocker.patch.object(off_eng._notifier, "transcription_succeeded")
        off_text = self._run_cycle(off_eng, tmp_path, chunks)

        assert off_text == live_text == live_typed_concat == "Des tickets, qui se baladent."
        inject.assert_called_once_with("Des tickets, qui se baladent.")

    def test_empty_chunk_does_not_shift_the_pending_separator(self, config_path, mocker, tmp_path):
        # 4.5: a chunk yielding no text must not consume or shift the pending
        # separator -- the next chunk's prefix is decided by the last boundary
        # that actually produced typed text, not by the chunk in between.
        eng = _make_toggle_streaming_engine(config_path, mocker)
        mocker.patch.object(eng._audio_engine, "transcribe", side_effect=["Alpha.", None, "Beta"])
        inject = mocker.patch.object(eng._text_injector, "inject")
        eng._on_fsm_recording(None)

        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "a.wav"), CONTINUATION)
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "b.wav"), SENTENCE)  # yields no text
        eng._transcribe_and_inject_chunk(_chunk_file(tmp_path, "c.wav"), SENTENCE)

        # The empty middle chunk injected nothing and left `_prev_boundary` /
        # `_pending_period` exactly as chunk "a" set them, so "Beta" is still
        # joined as a continuation of "Alpha." rather than as a fresh sentence.
        assert [c.args[0] for c in inject.call_args_list] == ["Alpha", ", beta"]
        assert eng._chunk_texts == ["Alpha", ", beta"]


# ---------------------------------------------------------------------------
# Tap re-arm reporting (fix-toggle-trigger-strand)
# ---------------------------------------------------------------------------


class TestTapRearmReporting:
    """A tap outage during a toggle-mode recording is reported, never guessed at."""

    def test_rearm_during_toggle_recording_is_reported(self, engine, caplog):
        engine._trigger_mode = "toggle"
        engine._state_machine.start_recording()

        with caplog.at_level(logging.WARNING, logger="whispy.core.engine"):
            engine._handle_tap_rearm()

        assert "stop-press may have been lost" in caplog.text
        # Reported, not resolved: synthesizing a press here would end a
        # dictation the user may still be speaking into.
        assert engine._state_machine.is_recording is True

    def test_rearm_while_idle_is_not_reported_as_a_lost_press(self, engine, caplog):
        engine._trigger_mode = "toggle"
        assert engine._state_machine.is_idle

        with caplog.at_level(logging.WARNING, logger="whispy.core.engine"):
            engine._handle_tap_rearm()

        assert "stop-press may have been lost" not in caplog.text

    def test_rearm_in_hold_mode_is_not_reported(self, engine, caplog):
        """Hold mode recovers a missed release from live flags — nothing to report."""
        engine._trigger_mode = "hold"
        engine._state_machine.start_recording()

        with caplog.at_level(logging.WARNING, logger="whispy.core.engine"):
            engine._handle_tap_rearm()

        assert "stop-press may have been lost" not in caplog.text

    def test_listener_rearm_reaches_the_engine(self, engine, caplog):
        """The hook is wired to the listener path that fires on a recovery."""
        from whispy.hardware import event_tap as et

        listener = et.EventTapListener(trigger_keycode=61)
        listener._tap = MagicMock()
        listener.on_rearm = engine._handle_tap_rearm
        engine._trigger_mode = "toggle"
        engine._state_machine.start_recording()

        with (
            caplog.at_level(logging.WARNING, logger="whispy.core.engine"),
            patch.object(et, "CGEventTapIsEnabled", return_value=False),
            patch.object(et, "CGEventTapEnable"),
            patch.object(listener, "_resync_after_rearm"),
        ):
            listener.check_tap_liveness()

        assert "stop-press may have been lost" in caplog.text

    def test_a_raising_rearm_hook_does_not_kill_the_listener(self):
        from whispy.hardware import event_tap as et

        listener = et.EventTapListener(trigger_keycode=61)
        listener._tap = MagicMock()
        listener.on_rearm = MagicMock(side_effect=RuntimeError("boom"))

        with (
            patch.object(et, "CGEventTapIsEnabled", return_value=False),
            patch.object(et, "CGEventTapEnable"),
            patch.object(listener, "_resync_after_rearm"),
        ):
            assert listener.check_tap_liveness() is True


# ---------------------------------------------------------------------------
# Config merge on save (fix-config-merge-on-save)
# ---------------------------------------------------------------------------


class TestConfigMergeOnSave:
    """An update merges onto the current on-disk config, never overwrites it.

    The file is read once at startup, so persisting the in-memory copy replays a
    boot-time snapshot over every later edit. Most keys have no UI, so editing
    the file is the only way to set them -- and that is exactly what a snapshot
    rewrite destroyed.
    """

    @staticmethod
    def _hand_edit(config_path, **keys):
        """Simulate the user editing config.json while the app is running."""
        on_disk = json.loads(config_path.read_text()) if config_path.exists() else {}
        on_disk.update(keys)
        config_path.write_text(json.dumps(on_disk))

    def test_a_key_edited_on_disk_survives_an_unrelated_update(self, engine, config_path):
        engine.update_config({"pause_ms": 800})  # establish a file
        assert engine.state.config["max_chunk_s"] != 20.0

        self._hand_edit(config_path, max_chunk_s=20.0)
        engine.update_config({"type_while_speaking": False})

        on_disk = json.loads(config_path.read_text())
        assert on_disk["max_chunk_s"] == 20.0, "the hand-edit must survive"
        assert on_disk["type_while_speaking"] is False
        assert engine.state.config["max_chunk_s"] == 20.0

    def test_the_update_wins_over_the_file_for_keys_it_names(self, engine, config_path):
        engine.update_config({"pause_ms": 800})
        self._hand_edit(config_path, pause_ms=500)

        engine.update_config({"pause_ms": 900})

        assert json.loads(config_path.read_text())["pause_ms"] == 900
        assert engine.state.config["pause_ms"] == 900

    def test_a_malformed_on_disk_value_is_not_merged_in_unchecked(self, engine, config_path):
        from whispy.core.config import DEFAULT_CONFIG

        engine.update_config({"pause_ms": 800})
        self._hand_edit(config_path, vad_aggressiveness="loud")

        engine.update_config({"type_while_speaking": False})  # must not raise

        on_disk = json.loads(config_path.read_text())
        assert on_disk["vad_aggressiveness"] == DEFAULT_CONFIG["vad_aggressiveness"]

    def test_the_shared_config_object_is_mutated_not_replaced(self, engine):
        # AudioEngine and the menu bar hold this dict by reference; rebinding it
        # would leave them reading a detached copy.
        before = engine.state.config
        engine.update_config({"pause_ms": 850})
        assert engine.state.config is before
        assert engine.state.config["pause_ms"] == 850

    def test_a_merged_in_streaming_value_reaches_the_audio_engine(self, engine, config_path, mocker):
        engine.update_config({"pause_ms": 800})
        apply_streaming = mocker.patch.object(engine, "_apply_streaming_config")

        # max_chunk_s is a streaming key; copy_to_clipboard is not.
        self._hand_edit(config_path, max_chunk_s=20.0)
        engine.update_config({"copy_to_clipboard": True})

        apply_streaming.assert_called_once()
        assert engine.state.config["max_chunk_s"] == 20.0

    def test_an_update_that_changes_nothing_performs_no_side_effects(self, engine, mocker):
        engine.update_config({"trigger_mode": "toggle", "pause_ms": 800})
        apply_streaming = mocker.patch.object(engine, "_apply_streaming_config")
        stop_listener = mocker.patch.object(engine, "stop_fn_listener")
        engine.state.fn_listener_active = True
        current_trigger = engine.state.config["trigger"]

        # Every value already matches: nothing changed, so nothing re-wires.
        engine.update_config({"trigger_mode": "toggle", "trigger": current_trigger})

        apply_streaming.assert_not_called()
        stop_listener.assert_not_called()

    def test_a_corrupt_file_at_update_time_does_not_raise(self, engine, config_path):
        from whispy.core.config import DEFAULT_CONFIG

        engine.update_config({"pause_ms": 800})
        assert DEFAULT_CONFIG["pause_ms"] != 800
        config_path.write_text("{ not json")

        engine.update_config({"type_while_speaking": False})  # must not raise

        on_disk = json.loads(config_path.read_text())
        assert on_disk["type_while_speaking"] is False

    def test_a_corrupt_file_does_not_reset_the_settings_the_engine_is_running(self, engine, config_path):
        # An unparseable file read as DEFAULT_CONFIG would have the next
        # unrelated toggle persist those defaults over everything the user set.
        # The running config is the fallback, so the toggle costs nothing else.
        from whispy.core.config import DEFAULT_CONFIG

        engine.update_config({"pause_ms": 800, "max_chunk_s": 20.0})
        config_path.write_text("{ not json")

        engine.update_config({"type_while_speaking": False})

        on_disk = json.loads(config_path.read_text())
        assert on_disk["pause_ms"] == 800
        assert on_disk["max_chunk_s"] == 20.0
        assert on_disk["pause_ms"] != DEFAULT_CONFIG["pause_ms"]
        assert engine.state.config["pause_ms"] == 800

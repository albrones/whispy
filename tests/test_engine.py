"""Tests for Engine, DictationState, config loading/saving, and status reporting."""

import json
import threading

from whispy.core.engine import (
    DEFAULT_CONFIG,
    DictationState,
    load_config,
    save_config,
)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Test load_config behavior."""

    def test_valid_config_file(self, tmp_dir):
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"model_size": "base", "language": "fr"}))

        loaded = load_config(config_file)
        assert loaded["model_size"] == "base"
        assert loaded["language"] == "fr"

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
        config_file.write_text(json.dumps({"model_size": "medium"}))

        loaded = load_config(config_file)
        assert loaded["model_size"] == "medium"
        assert loaded["language"] == "fr"

    def test_unknown_keys_in_config_are_ignored(self, tmp_dir):
        config_dir = tmp_dir / ".config" / "whispy"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"model_size": "tiny", "unknown_key": 42}))

        loaded = load_config(config_file)
        assert loaded["model_size"] == "tiny"
        assert "unknown_key" not in loaded

    def test_all_default_keys_present(self, tmp_dir):
        config_file = tmp_dir / "nonexistent" / "config.json"
        loaded = load_config(config_file)
        for key in DEFAULT_CONFIG:
            assert key in loaded

    def test_default_language_is_french(self, tmp_dir):
        config_file = tmp_dir / "nonexistent" / "config.json"
        loaded = load_config(config_file)
        assert loaded["language"] == "fr"
        assert DEFAULT_CONFIG["language"] == "fr"

    def test_default_copy_to_clipboard_is_false(self, tmp_dir):
        config_file = tmp_dir / "nonexistent" / "config.json"
        loaded = load_config(config_file)
        assert loaded["copy_to_clipboard"] is False
        assert DEFAULT_CONFIG["copy_to_clipboard"] is False


# ---------------------------------------------------------------------------
# Config saving
# ---------------------------------------------------------------------------


class TestSaveConfig:
    """Test save_config behavior."""

    def test_saves_correct_json(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["model_size"] = "base"
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["model_size"] == "base"

    def test_creates_directory_if_missing(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config_path = tmp_path / "subdir" / "config.json"
        save_config(config, config_path)
        assert config_path.exists()

    def test_writes_json_to_disk(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["model_size"] = "base"
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        content = config_path.read_text()
        assert '"model_size": "base"' in content

    def test_overwrites_existing_config(self, tmp_path):
        """Test that save_config overwrites the config at the given path."""
        config_path = tmp_path / "config.json"
        # Write a known config first
        config_path.write_text(json.dumps({"model_size": "tiny", "language": "en"}))

        save_config(dict(DEFAULT_CONFIG), config_path)
        saved = json.loads(config_path.read_text())
        assert saved["model_size"] == "small"
        assert saved["language"] == "fr"


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
        engine.update_config({"model_size": "base"})
        assert engine.state.config["model_size"] == "base"

    def test_update_saves_to_disk(self, engine, config_path):
        # Verify save_config writes to the exact path passed to Engine
        assert engine._config_path == config_path
        engine.update_config({"model_size": "base"})
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["model_size"] == "base"

    def test_update_returns_true_on_model_size_change(self, engine):
        result = engine.update_config({"model_size": "base"})
        assert result is True

    def test_update_returns_false_on_only_copy_to_clipboard_change(self, engine):
        result = engine.update_config({"copy_to_clipboard": False})
        assert result is False

    def test_update_updates_injector(self, engine):
        engine.update_config({"copy_to_clipboard": False})
        assert engine._text_injector._copy_to_clipboard is False

    def test_update_with_multiple_keys(self, engine):
        result = engine.update_config({"model_size": "base", "language": "fr"})
        assert result is True
        assert engine.state.config["model_size"] == "base"
        assert engine.state.config["language"] == "fr"

    def test_settings_survive_restart(self, engine, config_path):
        """Selecting settings then reloading from disk (a restart) keeps them.

        Guards the persistence path end-to-end: update_config -> save_config ->
        load_config returns the chosen values, not the defaults.
        """
        engine.update_config(
            {"model_size": "base", "language": "en", "copy_to_clipboard": True}
        )

        # Simulate a fresh process start: read the same file from scratch.
        reloaded = load_config(config_path)

        assert reloaded["model_size"] == "base"
        assert reloaded["language"] == "en"
        assert reloaded["copy_to_clipboard"] is True
        # And they differ from the shipped defaults, so this isn't a false pass.
        assert reloaded["language"] != DEFAULT_CONFIG["language"]


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
# custom_vocabulary -> initial_prompt wiring
# ---------------------------------------------------------------------------


class TestCustomVocabularyWiring:
    """run_transcription builds an initial_prompt from custom_vocabulary."""

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

    def test_vocabulary_builds_initial_prompt(self, engine, mocker, tmp_path):
        transcribe = self._prep(engine, mocker, tmp_path)
        engine.state.config["custom_vocabulary"] = ["Whispy", "ctranslate2"]

        engine.run_transcription()

        assert transcribe.call_args[1]["initial_prompt"] == "Whispy, ctranslate2"

    def test_empty_vocabulary_passes_none(self, engine, mocker, tmp_path):
        transcribe = self._prep(engine, mocker, tmp_path)
        engine.state.config["custom_vocabulary"] = []

        engine.run_transcription()

        assert transcribe.call_args[1]["initial_prompt"] is None


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

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stray trigger release does not start transcription (fix-capture-thread-races)
# ---------------------------------------------------------------------------


class TestTriggerReleaseGating:
    """_handle_trigger_release only wakes the worker on a real stop."""

    def test_release_while_recording_sets_stop_event(self, engine):
        engine.state.stop_event.clear()
        engine._state_machine.start_recording()  # enter RECORDING
        engine._handle_trigger_release()
        assert engine.state.stop_event.is_set()

    def test_stray_release_does_not_set_stop_event(self, engine):
        # No active recording (FSM IDLE): a release must be a no-op so the
        # worker never transcribes a stale/missing file.
        engine.state.stop_event.clear()
        assert engine._state_machine.current_state == State.IDLE
        engine._handle_trigger_release()
        assert not engine.state.stop_event.is_set()


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

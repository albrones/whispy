"""Tests for Engine, DictationState, config loading/saving, and status reporting."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from whispy.core.engine import (
    DEFAULT_CONFIG,
    DictationState,
    Engine,
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
        # Defaults preserved
        assert loaded["compute_key"] == "cpu-int8"

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
        assert loaded["compute_key"] == "cpu-int8"

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
        assert saved["compute_key"] == "cpu-int8"

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
        result = engine.update_config({"model_size": "base"})
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

    def test_update_returns_true_on_compute_key_change(self, engine):
        result = engine.update_config({"compute_key": "cpu-float32"})
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
# Helpers
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock

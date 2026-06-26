"""Tests for config validation in save_config and restart path resolution."""

import json
import sys
from pathlib import Path

# Ensure src/ is on the path
_src = Path(__file__).parent.parent / "src"
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.config import _validate_config
from whispy.core.engine import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
)

# ---------------------------------------------------------------------------
# min_recording_duration validation
# ---------------------------------------------------------------------------


class TestMinRecordingDuration:
    """Test validation of the min_recording_duration config key."""

    def test_default_present(self):
        assert DEFAULT_CONFIG["min_recording_duration"] == 0.3

    def test_valid_value_preserved(self):
        validated = _validate_config({"min_recording_duration": 0.5})
        assert validated["min_recording_duration"] == 0.5

    def test_negative_value_reset_to_default(self):
        validated = _validate_config({"min_recording_duration": -1})
        assert validated["min_recording_duration"] == 0.3

    def test_non_numeric_reset_to_default(self):
        validated = _validate_config({"min_recording_duration": "fast"})
        assert validated["min_recording_duration"] == 0.3

    def test_bool_reset_to_default(self):
        validated = _validate_config({"min_recording_duration": True})
        assert validated["min_recording_duration"] == 0.3


# ---------------------------------------------------------------------------
# save_config filtering
# ---------------------------------------------------------------------------


class TestSaveConfigFiltering:
    """Test that save_config filters unknown keys."""

    def test_unknown_keys_are_filtered(self, tmp_path):
        config = {**DEFAULT_CONFIG, "unknown_key": 42, "another_bad": "value"}
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert "unknown_key" not in saved
        assert "another_bad" not in saved

    def test_valid_configs_pass_through_unchanged(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["model_size"] = "base"
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert saved["model_size"] == "base"
        assert saved["language"] == "fr"
        for key in DEFAULT_CONFIG:
            assert key in saved

    def test_mixed_valid_invalid_configs_save_only_valid(self, tmp_path):
        config = {
            "model_size": "tiny",
            "language": "en",
            "copy_to_clipboard": True,
            "unknown_key": "should_not_appear",
            "beam_size": 5,
        }
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert saved["model_size"] == "tiny"
        assert saved["language"] == "en"
        assert saved["copy_to_clipboard"] is True
        assert saved["beam_size"] == 5
        assert "unknown_key" not in saved

    def test_empty_config_uses_all_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config({}, config_path)

        saved = json.loads(config_path.read_text())
        for key in DEFAULT_CONFIG:
            assert saved[key] == DEFAULT_CONFIG[key]


# ---------------------------------------------------------------------------
# custom_vocabulary validation
# ---------------------------------------------------------------------------


class TestCustomVocabulary:
    """Test validation of the custom_vocabulary config key."""

    def test_default_is_empty_list(self):
        assert DEFAULT_CONFIG["custom_vocabulary"] == []

    def test_valid_list_preserved(self):
        validated = _validate_config({"custom_vocabulary": ["Whispy", "ctranslate2"]})
        assert validated["custom_vocabulary"] == ["Whispy", "ctranslate2"]

    def test_non_list_falls_back_to_empty(self):
        validated = _validate_config({"custom_vocabulary": "Whispy"})
        assert validated["custom_vocabulary"] == []

    def test_non_string_entries_filtered_and_stripped(self):
        validated = _validate_config({"custom_vocabulary": ["  Whispy  ", 42, "", None, "sox"]})
        assert validated["custom_vocabulary"] == ["Whispy", "sox"]


# ---------------------------------------------------------------------------
# Restart path resolution
# ---------------------------------------------------------------------------


class TestRestartPath:
    """Test that the restart path resolves correctly."""

    def test_restart_path_resolves_to_existing_file(self):
        """The restart path (whispy_daemon.py) should exist at project root."""
        from whispy.core.paths import resolve_daemon_script

        script_path = resolve_daemon_script()
        assert script_path.exists(), f"Restart script not found at {script_path}"

    def test_whispy_py_does_not_exist(self):
        """Verify whispy.py does NOT exist (should use whispy_daemon.py)."""
        from whispy.core.paths import resolve_daemon_script

        old_path = resolve_daemon_script().parent / "whispy.py"
        assert not old_path.exists(), "whispy.py should not exist"


# ---------------------------------------------------------------------------
# Streaming / incremental transcription config
# ---------------------------------------------------------------------------


class TestStreamingConfig:
    """Validation and migration of the streaming config keys."""

    def test_defaults_present(self):
        assert DEFAULT_CONFIG["streaming_enabled"] is True
        assert DEFAULT_CONFIG["pause_ms"] == 600
        assert DEFAULT_CONFIG["min_chunk_s"] == 0.4
        assert DEFAULT_CONFIG["max_chunk_s"] == 12.0
        assert DEFAULT_CONFIG["vad_aggressiveness"] == 2

    def test_valid_values_preserved(self):
        validated = _validate_config(
            {
                "streaming_enabled": False,
                "pause_ms": 400,
                "min_chunk_s": 0.5,
                "max_chunk_s": 20.0,
                "vad_aggressiveness": 3,
            }
        )
        assert validated["streaming_enabled"] is False
        assert validated["pause_ms"] == 400
        assert validated["min_chunk_s"] == 0.5
        assert validated["max_chunk_s"] == 20.0
        assert validated["vad_aggressiveness"] == 3

    def test_streaming_enabled_non_bool_resets(self):
        assert _validate_config({"streaming_enabled": "yes"})["streaming_enabled"] is True

    def test_pause_ms_non_positive_resets(self):
        assert _validate_config({"pause_ms": 0})["pause_ms"] == 600
        assert _validate_config({"pause_ms": -100})["pause_ms"] == 600
        assert _validate_config({"pause_ms": True})["pause_ms"] == 600

    def test_min_chunk_s_negative_resets(self):
        assert _validate_config({"min_chunk_s": -1})["min_chunk_s"] == 0.4

    def test_max_chunk_s_must_exceed_min_chunk_s(self):
        # max <= min is invalid -> reset to default
        assert _validate_config({"min_chunk_s": 5.0, "max_chunk_s": 3.0})["max_chunk_s"] == 12.0

    def test_vad_aggressiveness_out_of_range_resets(self):
        assert _validate_config({"vad_aggressiveness": 9})["vad_aggressiveness"] == 2
        assert _validate_config({"vad_aggressiveness": -1})["vad_aggressiveness"] == 2
        assert _validate_config({"vad_aggressiveness": True})["vad_aggressiveness"] == 2

    def test_migration_adds_streaming_keys(self, tmp_path):
        import json

        config_file = tmp_path / "config.json"
        # A pre-streaming config without the new keys.
        config_file.write_text(json.dumps({"model_size": "small", "_version": 0}))

        loaded = load_config(config_file)
        for key in ("streaming_enabled", "pause_ms", "min_chunk_s", "max_chunk_s", "vad_aggressiveness"):
            assert key in loaded
        # And the defaults were persisted back.
        on_disk = json.loads(config_file.read_text())
        assert "streaming_enabled" in on_disk

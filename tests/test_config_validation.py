"""Tests for config validation in save_config and restart path resolution."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the path
_src = Path(__file__).parent.parent / "src"
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.engine import (
    DEFAULT_CONFIG,
    save_config,
)


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
# Restart path resolution
# ---------------------------------------------------------------------------


class TestRestartPath:
    """Test that the restart path resolves correctly."""

    def test_restart_path_resolves_to_existing_file(self):
        """The restart path (whispy_daemon.py) should exist at project root."""
        from whispy.ui.menu_bar import ICONS_DIR

        script_path = ICONS_DIR.parent.parent / "whispy_daemon.py"
        assert script_path.exists(), f"Restart script not found at {script_path}"

    def test_whispy_py_does_not_exist(self):
        """Verify whispy.py does NOT exist (should use whispy_daemon.py)."""
        from whispy.ui.menu_bar import ICONS_DIR

        old_path = ICONS_DIR.parent / "whispy.py"
        assert not old_path.exists(), "whispy.py should not exist"

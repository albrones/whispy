"""Tests for simplified configuration UI — no trigger_key or compute_key."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the path and mock macOS-only deps
_src = Path(__file__).parent.parent / "src"
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
if "" in sys.path and str(Path(".").resolve()) == Path(_project_root).resolve():
    sys.path.remove("")
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

if "Quartz" not in sys.modules:
    sys.modules["Quartz"] = MagicMock()
if "rumps" not in sys.modules:
    sys.modules["rumps"] = MagicMock()

from whispy.core.engine import DEFAULT_CONFIG, Engine, DictationState


class TestDefaultConfigNoDeprecatedKeys:
    """DEFAULT_CONFIG must not contain compute_key or trigger_key."""

    def test_no_compute_key_in_default_config(self):
        assert "compute_key" not in DEFAULT_CONFIG

    def test_no_trigger_key_in_default_config(self):
        assert "trigger_key" not in DEFAULT_CONFIG


class TestTriggerKeycodeAlwaysFn:
    """Engine._trigger_keycode_from_config must always return 63."""

    def test_returns_63_with_empty_state(self, tmp_path):
        state = DictationState()
        engine = Engine(state, tmp_path / "config.json")
        assert engine._trigger_keycode_from_config() == 63

    def test_returns_63_even_if_trigger_key_in_config(self, tmp_path):
        state = DictationState()
        state.config["trigger_key"] = "ampersand"
        engine = Engine(state, tmp_path / "config.json")
        assert engine._trigger_keycode_from_config() == 63


class TestUpdateConfigIgnoresDeprecatedKeys:
    """Engine.update_config must silently ignore compute_key and trigger_key."""

    def test_ignores_compute_key(self, tmp_path):
        state = DictationState()
        engine = Engine(state, tmp_path / "config.json")
        engine.update_config({"compute_key": "cpu-float32"})
        assert "compute_key" not in engine.state.config

    def test_ignores_trigger_key(self, tmp_path):
        state = DictationState()
        engine = Engine(state, tmp_path / "config.json")
        engine.update_config({"trigger_key": "capslock"})
        assert "trigger_key" not in engine.state.config


class TestEventTapNoLearningMode:
    """EventTapListener must not have learning mode methods."""

    def test_no_start_learning_method(self):
        from whispy.hardware.event_tap import EventTapListener
        listener = EventTapListener()
        assert not hasattr(listener, "start_learning")

    def test_no_stop_learning_method(self):
        from whispy.hardware.event_tap import EventTapListener
        listener = EventTapListener()
        assert not hasattr(listener, "stop_learning")

    def test_no_is_learning_property(self):
        from whispy.hardware.event_tap import EventTapListener
        listener = EventTapListener()
        assert not hasattr(listener, "is_learning")


class TestLanguageOnlyFrEn:
    """SUPPORTED_LANGUAGES must only contain fr and en."""

    def test_only_fr_and_en(self):
        from whispy.core.engine import SUPPORTED_LANGUAGES
        assert set(SUPPORTED_LANGUAGES.keys()) == {"fr", "en"}

    def test_no_auto_language(self):
        from whispy.core.engine import SUPPORTED_LANGUAGES
        assert "auto" not in SUPPORTED_LANGUAGES

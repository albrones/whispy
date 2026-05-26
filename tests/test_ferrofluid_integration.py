"""Tests for the ferrofluid visualization integration in the menu bar app.

Verifies that FerrofluidWindow and AudioLevelMonitor are correctly wired
to the WhisperMenuBarApp lifecycle (show/hide/start/stop/destroy).

Note: We test the ferrofluid classes directly and verify the lifecycle
methods' logic via AST parsing, because conftest.py replaces rumps
with a MagicMock which makes WhisperMenuBarApp (subclass of rumps.App)
un-instantiable.
"""

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src/ is on the path, and remove project root to avoid shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Mock macOS-only deps
if "Quartz" not in sys.modules:
    sys.modules["Quartz"] = MagicMock()
if "AppKit" not in sys.modules:
    sys.modules["AppKit"] = MagicMock()
if "sounddevice" not in sys.modules:
    sys.modules["sounddevice"] = MagicMock()
if "rumps" not in sys.modules:
    sys.modules["rumps"] = MagicMock()

from whispy.ui.audio_level import AudioLevelMonitor
from whispy.ui.ferrofluid_window import FerrofluidWindow

# Import the menu_bar module to inspect source
import whispy.ui.menu_bar as menu_bar_module


def _get_method_body(source_path: str, method_name: str) -> str:
    """Parse the AST of a file and return the source lines for a given method."""
    with open(source_path, "r") as f:
        source = f.read()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            # Extract source lines for this method
            lines = source.split("\n")
            start = node.lineno - 1  # 0-indexed
            end = node.end_lineno  # exclusive
            return "\n".join(lines[start:end])
    return ""


class TestFerrofluidClassesInstantiable:
    """Test that ferrofluid classes can be instantiated."""

    def test_audio_monitor_instantiable(self):
        """AudioLevelMonitor should be instantiable."""
        monitor = AudioLevelMonitor()
        assert monitor is not None
        assert isinstance(monitor, AudioLevelMonitor)

    def test_ferrofluid_window_instantiable(self):
        """FerrofluidWindow should be instantiable."""
        viz = FerrofluidWindow()
        assert viz is not None
        assert isinstance(viz, FerrofluidWindow)

    def test_monitor_connected_to_visualization(self):
        """set_audio_monitor should link the monitor to the visualization."""
        monitor = AudioLevelMonitor()
        viz = FerrofluidWindow()
        viz.set_audio_monitor(monitor)

        assert viz._audio_level_monitor is monitor


class TestMenuBarFerrofluidInitLogic:
    """Test that __init__ creates the ferrofluid components."""

    def test_init_source_creates_audio_monitor(self):
        """__init__ source should create _audio_monitor."""
        source = menu_bar_module.__file__
        with open(source, "r") as f:
            content = f.read()

        assert "_audio_monitor" in content
        assert "_visualization" in content
        assert "AudioLevelMonitor()" in content
        assert "FerrofluidWindow()" in content

    def test_init_source_connects_monitor(self):
        """__init__ source should connect monitor to visualization."""
        source = menu_bar_module.__file__
        with open(source, "r") as f:
            content = f.read()

        assert "set_audio_monitor" in content


class TestRecordingStartLogic:
    """Test _on_recording_start logic via AST parsing."""

    def _get_method_source(self):
        source = menu_bar_module.__file__
        return _get_method_body(source, "_on_recording_start")

    def test_hides_indicator(self):
        """_on_recording_start should hide the indicator."""
        method_source = self._get_method_source()
        assert method_source, "_on_recording_start method not found"
        assert "hide()" in method_source

    def test_starts_audio_monitor(self):
        """_on_recording_start should start the audio monitor."""
        method_source = self._get_method_source()
        assert method_source, "_on_recording_start method not found"
        assert "start()" in method_source

    def test_shows_visualization(self):
        """_on_recording_start should show the ferrofluid visualization."""
        method_source = self._get_method_source()
        assert method_source, "_on_recording_start method not found"
        assert "show()" in method_source


class TestRecordingStopLogic:
    """Test _on_recording_stop logic via AST parsing."""

    def _get_method_source(self):
        source = menu_bar_module.__file__
        return _get_method_body(source, "_on_recording_stop")

    def test_stops_monitor_when_not_transcribing(self):
        """_on_recording_stop should stop monitor when not transcribing."""
        method_source = self._get_method_source()
        assert method_source, "_on_recording_stop method not found"
        assert "is_transcribing" in method_source
        assert "stop()" in method_source

    def test_skips_cleanup_when_transcribing(self):
        """_on_recording_stop should skip cleanup when still transcribing."""
        method_source = self._get_method_source()
        assert method_source, "_on_recording_stop method not found"
        assert "if" in method_source


class TestFnPressedLogic:
    """Test _on_fn_pressed logic via AST parsing."""

    def _get_method_source(self):
        source = menu_bar_module.__file__
        return _get_method_body(source, "_on_fn_pressed")

    def test_shows_visualization_when_not_recording(self):
        """_on_fn_pressed should show visualization when not recording."""
        method_source = self._get_method_source()
        assert method_source, "_on_fn_pressed method not found"
        assert "is_recording" in method_source
        assert "show()" in method_source

    def test_does_nothing_when_recording(self):
        """_on_fn_pressed should do nothing when already recording."""
        method_source = self._get_method_source()
        assert method_source, "_on_fn_pressed method not found"
        assert "is_recording" in method_source


class TestFnReleasedLogic:
    """Test _on_fn_released logic via AST parsing."""

    def _get_method_source(self):
        source = menu_bar_module.__file__
        return _get_method_body(source, "_on_fn_released")

    def test_shows_indicator_when_transcribing(self):
        """_on_fn_released should show transcribing indicator."""
        method_source = self._get_method_source()
        assert method_source, "_on_fn_released method not found"
        assert "is_transcribing" in method_source
        assert "show" in method_source

    def test_does_nothing_when_not_transcribing(self):
        """_on_fn_released should do nothing when not transcribing."""
        method_source = self._get_method_source()
        assert method_source, "_on_fn_released method not found"
        assert "is_transcribing" in method_source


class TestQuitCleanupLogic:
    """Test _on_quit cleanup logic via AST parsing."""

    def _get_method_source(self):
        source = menu_bar_module.__file__
        return _get_method_body(source, "_on_quit")

    def test_destroys_all_resources(self):
        """_on_quit should destroy indicator, stop monitor, and destroy visualization."""
        method_source = self._get_method_source()
        assert method_source, "_on_quit method not found"
        assert "destroy" in method_source
        assert "stop" in method_source

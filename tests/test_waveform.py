"""Tests for the audio-reactive waveform visualization and its menu-bar wiring.

The view/window are exercised directly with real AppKit (available on the
macOS test runner). The menu-bar lifecycle is verified by source inspection
because conftest replaces rumps with a MagicMock, which makes the
rumps.App subclass un-instantiable.
"""

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock

from AppKit import NSMakeRect

import whispy.ui.menu_bar as menu_bar_module
from whispy.ui.waveform_window import WaveformView, WaveformWindow

# Mock Quartz/rumps (macOS-only) without clobbering AppKit/sounddevice.
if "Quartz" not in sys.modules:
    sys.modules["Quartz"] = MagicMock()
if "rumps" not in sys.modules:
    sys.modules["rumps"] = MagicMock()


def _method_body(method_name: str) -> str:
    source = Path(menu_bar_module.__file__).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            lines = source.split("\n")
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


class TestWaveformClasses:
    def test_window_instantiable(self):
        win = WaveformWindow()
        assert isinstance(win, WaveformWindow)

    def test_view_instantiable(self):
        view = WaveformView.alloc().initWithFrame_(NSMakeRect(0, 0, 168, 52))
        assert view is not None
        assert view._level == 0.0

    def test_set_audio_monitor_stored(self):
        win = WaveformWindow()
        monitor = MagicMock()
        win.set_audio_monitor(monitor)
        assert win._audio_monitor is monitor

    def test_tick_moves_level_toward_monitor(self):
        view = WaveformView.alloc().initWithFrame_(NSMakeRect(0, 0, 168, 52))
        monitor = MagicMock()
        monitor.get_level.return_value = 0.8
        view.set_audio_monitor(monitor)
        view.tick_(None)
        assert view._level > 0.0
        assert view._target_level == 0.8


class TestMenuBarWaveformWiring:
    def test_init_creates_waveform_components(self):
        content = Path(menu_bar_module.__file__).read_text()
        assert "_audio_monitor" in content
        assert "_visualization" in content
        assert "AudioLevelMonitor()" in content
        assert "WaveformWindow()" in content
        assert "set_audio_monitor" in content

    def test_recording_start_shows_visualization(self):
        body = _method_body("_on_recording_start")
        assert "hide()" in body
        assert "start()" in body
        assert "show()" in body

    def test_recording_stop_stops_when_not_transcribing(self):
        body = _method_body("_on_recording_stop")
        assert "is_transcribing" in body
        assert "stop()" in body

    def test_fn_pressed_shows_when_not_recording(self):
        body = _method_body("_on_fn_pressed")
        assert "is_recording" in body
        assert "show()" in body

    def test_quit_cleans_up(self):
        body = _method_body("_on_quit")
        assert "destroy" in body
        assert "stop" in body

"""E2E tests for the ferrofluid visualization pipeline.

Verifies the complete data flow:
  AudioLevelMonitor -> FerrofluidWindow -> FerrofluidView
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure src/ is on the path
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.ui.audio_level import AudioLevelMonitor
from whispy.ui.ferrofluid_view import FerrofluidView

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_view():
    """Create a FerrofluidView with a fake frame, mocking NSView superclass."""
    with patch("whispy.ui.ferrofluid_view.NSView"):
        view = FerrofluidView.__new__(FerrofluidView)
        view._audio_level = 0.0
        view._target_level = 0.0
        view._last_frame_time = time.monotonic()
        view._frame_count = 0
        view._spike_phase = 0.0
        view._audio_monitor = None
        view._sphere_radius = 50.0
        view._spike_count = 16
        view._max_spike_height = 45.0
        view._anim_timer = None
        view._fade_target = 0.0
        view._current_fade = 0.0
        return view


def _push_audio(monitor, amplitude: float, count: int = 10):
    """Simulate audio callback samples on a monitor (stream already patched)."""
    mock_status = type("Status", (), {"__bool__": lambda self: False})()
    indata = np.ones((1024, 1)) * amplitude
    for _ in range(count):
        monitor._audio_callback(indata, 1024, {}, mock_status)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFerrofluidViewAudioIntegration:
    """Test that FerrofluidView correctly reads audio levels from a monitor."""

    def test_view_initial_audio_level_is_zero(self):
        """Fresh view should have zero audio level."""
        view = _make_mock_view()
        assert view._audio_level == 0.0

    def test_set_audio_monitor_links_monitor_to_view(self):
        """set_audio_monitor should store the monitor reference."""
        monitor = MagicMock()
        view = _make_mock_view()
        view.set_audio_monitor(monitor)
        assert view._audio_monitor is monitor

    def test_draw_frame_reads_audio_level_from_monitor(self):
        """_draw_frame should pull get_level() from the monitor and update _audio_level."""
        monitor = AudioLevelMonitor(smoothing=0.0)  # no smoothing for predictability
        with patch.object(monitor, "_stream"):
            monitor._running = True

        view = _make_mock_view()
        view.set_audio_monitor(monitor)
        # Simulate audio input: rms = 1.0 -> normalized = min(1.0 * 10, 1.0) = 1.0
        _push_audio(monitor, amplitude=1.0, count=5)

        # Advance time so lerp actually moves
        view._last_frame_time -= 1.0  # dt = 1.0
        view._draw_frame()

        # _audio_level should have moved toward 1.0 (target = 1.0 from monitor)
        assert view._audio_level > 0.0, f"Expected audio_level > 0 after audio input, got {view._audio_level}"

    def test_draw_frame_with_no_monitor_keeps_zero(self):
        """Without a monitor, _audio_level should stay at 0 (no spikes)."""
        view = _make_mock_view()
        # No monitor set
        view._last_frame_time -= 1.0
        view._draw_frame()
        assert view._audio_level == 0.0

    def test_audio_level_increases_with_audio_intensity(self):
        """Higher audio amplitude should produce higher _audio_level after draw_frame."""
        monitor_loud = AudioLevelMonitor(smoothing=0.0)
        with patch.object(monitor_loud, "_stream"):
            monitor_loud._running = True
        _push_audio(monitor_loud, amplitude=1.0, count=5)

        monitor_quiet = AudioLevelMonitor(smoothing=0.0)
        with patch.object(monitor_quiet, "_stream"):
            monitor_quiet._running = True
        # amplitude=0.01 -> rms=0.01 -> normalized=min(0.1, 1.0)=0.1 (well below cap)
        _push_audio(monitor_quiet, amplitude=0.01, count=5)

        view_loud = _make_mock_view()
        view_loud.set_audio_monitor(monitor_loud)
        view_loud._last_frame_time -= 1.0
        view_loud._draw_frame()

        view_quiet = _make_mock_view()
        view_quiet.set_audio_monitor(monitor_quiet)
        view_quiet._last_frame_time -= 1.0
        view_quiet._draw_frame()

        assert view_loud._audio_level > view_quiet._audio_level, (
            f"Loud level ({view_loud._audio_level}) should exceed quiet level ({view_quiet._audio_level})"
        )

    def test_silent_audio_produces_zero_level(self):
        """Silence should keep audio_level at zero."""
        monitor = AudioLevelMonitor(smoothing=0.0)
        with patch.object(monitor, "_stream"):
            monitor._running = True
        _push_audio(monitor, amplitude=0.0, count=10)

        view = _make_mock_view()
        view.set_audio_monitor(monitor)
        view._last_frame_time -= 1.0
        view._draw_frame()

        assert view._audio_level == pytest.approx(0.0, abs=1e-9)


class TestFerrofluidWindowViewChain:
    """Test that FerrofluidWindow correctly passes the audio monitor to the view."""

    def test_window_stores_monitor_and_passes_to_view(self):
        """FerrofluidWindow should store the monitor and pass it to the view."""
        monitor = AudioLevelMonitor()
        with patch.object(monitor, "_stream"):
            monitor._running = True

        with patch("whispy.ui.ferrofluid_window.FerrofluidView") as MockView:
            mock_view = MagicMock()
            MockView.alloc().initWithFrame_.return_value = mock_view

            window = __import__("whispy.ui.ferrofluid_window", fromlist=["FerrofluidWindow"]).FerrofluidWindow()
            window.set_audio_monitor(monitor)
            window._initialized = False

            # Patch the NSWindow and NSWindowCollectionBehavior to avoid
            # pyobjc NewType issues during mock
            mock_window = MagicMock()
            with (
                patch("whispy.ui.ferrofluid_window.NSWindow") as MockWindow,
                patch("whispy.ui.ferrofluid_window.NSWindowCollectionBehavior") as MockBehavior,
                patch(
                    "whispy.ui.ferrofluid_window.NSBorderlessWindowMask",
                    default=0,
                ),
                patch(
                    "whispy.ui.ferrofluid_window.NSBackingStoreType",
                    new=1,
                ),
                patch(
                    "whispy.ui.ferrofluid_window.NSPopUpMenuWindowLevel",
                    default=20,
                ),
                patch("whispy.ui.ferrofluid_window.NSColor") as MockColor,
                patch("whispy.ui.ferrofluid_window.NSApplication") as MockApp,
            ):
                MockWindow.alloc().initWithContentRect_styleMask_backing_defer_.return_value = mock_window
                MockBehavior.canJoinAllSpaces = 1
                MockBehavior.stationary = 2
                MockBehavior.ignoresCycle = 4
                MockColor.colorWithSRGBRed_green_blue_alpha_.return_value = MagicMock()
                MockApp.sharedApplication.return_value.mainScreen.return_value = MagicMock(
                    visibleFrame=MagicMock(size=MagicMock(width=1920, height=1080))
                )

                window.show()

            # Verify set_audio_monitor was called on the view
            mock_view.set_audio_monitor.assert_called_with(monitor)

            # Verify animation was started
            mock_view.start_animation.assert_called()


class TestFullVisualizationPipeline:
    """E2E: full chain from audio input to view audio level."""

    def test_monitor_to_view_data_flow(self):
        """Simulate the complete pipeline: audio -> monitor -> view -> _audio_level."""
        # 1. Create monitor and simulate audio
        monitor = AudioLevelMonitor(smoothing=0.0)
        with patch.object(monitor, "_stream"):
            monitor._running = True

        # Simulate moderate audio input
        _push_audio(monitor, amplitude=0.5, count=20)

        # 2. Create view and link monitor
        view = _make_mock_view()
        view.set_audio_monitor(monitor)

        # 3. Run one frame
        view._last_frame_time -= 1.0
        view._draw_frame()

        # 4. Verify the audio level propagated
        assert view._audio_level > 0.0, f"Audio level should be > 0 after moderate audio input, got {view._audio_level}"

    def test_full_pipeline_with_varying_audio(self):
        """Test that the view responds to changing audio levels over multiple frames."""
        monitor = AudioLevelMonitor(smoothing=0.0)
        with patch.object(monitor, "_stream"):
            monitor._running = True

        view = _make_mock_view()
        view.set_audio_monitor(monitor)

        # Frame 1: silence
        view._last_frame_time -= 1.0
        view._draw_frame()
        level_silent = view._audio_level

        # Frame 2: introduce audio
        _push_audio(monitor, amplitude=0.8, count=10)
        view._last_frame_time -= 1.0
        view._draw_frame()
        level_with_audio = view._audio_level

        # Frame 3: louder audio
        _push_audio(monitor, amplitude=1.0, count=10)
        view._last_frame_time -= 1.0
        view._draw_frame()
        level_loud = view._audio_level

        assert level_with_audio > level_silent, f"Audio should increase level: {level_with_audio} vs {level_silent}"
        assert level_loud >= level_with_audio, (
            f"Louder audio should not decrease level: {level_loud} vs {level_with_audio}"
        )

"""Tests for the audio level monitor module."""

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from whispy.ui.audio_level import AudioLevelMonitor


class TestAudioLevelMonitor:
    """Tests for AudioLevelMonitor."""

    def test_initial_state(self):
        """Monitor should start in not-running state."""
        monitor = AudioLevelMonitor()
        assert monitor.is_running is False
        # get_level should return 0.0 when not running
        assert monitor.get_level() == 0.0

    def test_start_returns_false_when_already_running(self):
        """Starting an already-running monitor should return False."""
        monitor = AudioLevelMonitor()
        with patch.object(monitor, "_stream"):
            monitor._running = True
            assert monitor.start() is False

    def test_get_level_returns_smoothed_value(self):
        """get_level should return the smoothed audio level."""
        monitor = AudioLevelMonitor(smoothing=0.5)
        # Simulate audio callback directly
        with patch.object(monitor, "_stream"):
            monitor._running = True
            # Simulate a callback with audio data
            indata = np.ones((1024, 1)) * 0.1
            # Pass a falsy status object (no errors)
            mock_status = type("Status", (), {"__bool__": lambda self: False})()
            monitor._audio_callback(indata, 1024, {}, mock_status)
            level = monitor.get_level()
            # Expected: rms = 0.1, normalized = min(0.1 * 10, 1.0) = 1.0
            # First value: 0.5 * 0 + 0.5 * 1.0 = 0.5
            assert level == pytest.approx(0.5, abs=0.01)

    def test_get_level_clamps_to_1_0(self):
        """Very loud audio should not exceed 1.0."""
        monitor = AudioLevelMonitor(smoothing=0.5)
        with patch.object(monitor, "_stream"):
            monitor._running = True
            indata = np.ones((1024, 1)) * 10.0  # Very loud
            monitor._audio_callback(indata, 1024, {}, type("Status", (), {})())
            level = monitor.get_level()
            assert level <= 1.0

    def test_get_level_returns_0_for_silence(self):
        """Silent audio should produce 0.0 level."""
        monitor = AudioLevelMonitor(smoothing=0.5)
        with patch.object(monitor, "_stream"):
            monitor._running = True
            indata = np.zeros((1024, 1))
            monitor._audio_callback(indata, 1024, {}, type("Status", (), {})())
            level = monitor.get_level()
            assert level == 0.0

    def test_smoothing_reduces_jitter(self):
        """High smoothing factor should produce gradual changes."""
        monitor = AudioLevelMonitor(smoothing=0.9)
        with patch.object(monitor, "_stream"):
            monitor._running = True
            mock_status = type("Status", (), {"__bool__": lambda self: False})()
            # First callback: loud
            indata_loud = np.ones((1024, 1))
            monitor._audio_callback(indata_loud, 1024, {}, mock_status)
            level1 = monitor.get_level()

            # Second callback: silence
            indata_silent = np.zeros((1024, 1))
            monitor._audio_callback(indata_silent, 1024, {}, mock_status)
            level2 = monitor.get_level()

            # With high smoothing, level2 should still be relatively high
            # (not immediately drop to 0)
            assert level2 > level1 * 0.5

    def test_concurrent_get_level(self):
        """get_level should be thread-safe under concurrent access."""
        monitor = AudioLevelMonitor()
        with patch.object(monitor, "_stream"):
            monitor._running = True

            errors = []

            def writer():
                indata = np.ones((1024, 1))
                for _ in range(100):
                    try:
                        monitor._audio_callback(indata, 1024, {}, type("Status", (), {})())
                    except Exception as e:
                        errors.append(e)

            def reader():
                for _ in range(100):
                    try:
                        monitor.get_level()
                    except Exception as e:
                        errors.append(e)

            t1 = threading.Thread(target=writer)
            t2 = threading.Thread(target=reader)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            assert len(errors) == 0

    def test_stop_releases_monitor(self):
        """stop() should set _running to False and close the stream."""
        mock_stream = MagicMock()
        monitor = AudioLevelMonitor()
        monitor._stream = mock_stream
        monitor._running = True
        monitor.stop()

        assert monitor.is_running is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_stop_when_not_running_does_nothing(self):
        """Calling stop() on a non-running monitor should be a no-op."""
        monitor = AudioLevelMonitor()
        monitor._running = False
        monitor._stream = None
        # Should not raise
        monitor.stop()
        assert monitor.is_running is False

"""Unit tests for the pure audio-level math (no sounddevice)."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.ui.level_math import rms_to_level


class TestRmsToLevel:
    def test_clamps_normalized_to_one(self):
        # rms * 10 = 5.0 -> clamped to 1.0; with prev=1.0 stays 1.0
        assert rms_to_level(0.5, prev_smoothed=1.0, smoothing=0.85) == 1.0

    def test_ema_formula(self):
        # normalized = min(0.02*10, 1.0) = 0.2; 0.85*0.0 + 0.15*0.2 = 0.03
        result = rms_to_level(0.02, prev_smoothed=0.0, smoothing=0.85)
        assert abs(result - 0.03) < 1e-9

    def test_zero_rms_decays_toward_zero(self):
        # silence pulls the smoothed level down
        result = rms_to_level(0.0, prev_smoothed=0.8, smoothing=0.85)
        assert abs(result - 0.68) < 1e-9  # 0.85 * 0.8

    def test_full_smoothing_holds_previous(self):
        assert rms_to_level(0.05, prev_smoothed=0.4, smoothing=1.0) == 0.4

    def test_no_smoothing_uses_normalized(self):
        # smoothing=0 -> result is the normalized value
        assert abs(rms_to_level(0.03, prev_smoothed=0.9, smoothing=0.0) - 0.3) < 1e-9

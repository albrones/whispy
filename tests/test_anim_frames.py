"""Unit tests for the pure animation frame selection."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.ui.unicode_anim import IDLE_FRAME, WAVEROWS, select_frame


class TestSelectFrame:
    def test_active_returns_indexed_frame(self):
        assert select_frame(0, is_active=True) == WAVEROWS[0]
        assert select_frame(3, is_active=True) == WAVEROWS[3]

    def test_active_wraps_modulo_frame_count(self):
        n = len(WAVEROWS)
        assert select_frame(n, is_active=True) == WAVEROWS[0]
        assert select_frame(n + 5, is_active=True) == WAVEROWS[5]

    def test_inactive_returns_idle_frame(self):
        assert select_frame(0, is_active=False) == IDLE_FRAME
        assert select_frame(99, is_active=False) == IDLE_FRAME

"""UI modules for Whispy's macOS menu bar and visualization.

This is the macOS UI surface (rumps menu bar + AppKit overlay). The overlay
modules depend on AppKit/objc, absent on Linux — so the eager re-exports are
import-tolerant: on a platform without the GUI stack the package still imports
(and pure submodules like ``level_math``/``unicode_anim`` stay importable
directly); the AppKit-coupled names simply aren't re-exported there.
"""

__all__ = []

try:
    from .audio_level import AudioLevelMonitor  # noqa: F401

    __all__.append("AudioLevelMonitor")
except ImportError:  # pragma: no cover - missing audio backend
    pass

try:
    from .waveform_window import WaveformWindow  # noqa: F401

    __all__.append("WaveformWindow")
except ImportError:  # pragma: no cover - missing AppKit/objc (non-macOS)
    pass

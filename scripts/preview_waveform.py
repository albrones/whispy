#!/usr/bin/env python3
"""Standalone preview of the waveform window — no daemon, no Fn key, no mic.

Run it to check whether the floating pill renders at all:

    ./.venv/bin/python scripts/preview_waveform.py

You should see a black rounded pill near the bottom-center of the screen with
purple bars oscillating for ~10 seconds. Any error is printed to the console.
Press Ctrl+C to quit early.
"""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory  # noqa: E402
from PyObjCTools import AppHelper  # noqa: E402

from whispy.ui.waveform_window import WaveformWindow  # noqa: E402


class FakeMonitor:
    """Returns an oscillating level so the bars visibly move."""

    def __init__(self):
        self._t0 = time.monotonic()

    def get_level(self):
        t = time.monotonic() - self._t0
        return 0.5 + 0.5 * math.sin(t * 3.0)


def main():
    app = NSApplication.sharedApplication()
    # Accessory: no Dock icon, but windows still display (like the daemon).
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    win = WaveformWindow()
    win.set_audio_monitor(FakeMonitor())
    win.show()
    print("[preview] window.show() called — look at the bottom-center of the screen.")
    print("[preview] window visible:", win._window.isVisible() if win._window else None)
    print("[preview] window frame:", win._window.frame() if win._window else None)

    # Quit automatically after 10s.
    AppHelper.callLater(10.0, AppHelper.stopEventLoop)
    AppHelper.runEventLoop()
    print("[preview] done.")


if __name__ == "__main__":
    main()

"""Bottom-centered audio-reactive waveform indicator.

A small rounded "pill" window that floats near the bottom of the screen and
shows vertical bars reacting to the microphone level while recording. Rendering
uses NSBezierPath/NSColor (plain AppKit) so it draws reliably inside drawRect_
without juggling CoreGraphics contexts.

`WaveformWindow` exposes the same lifecycle as the menu bar expects:
``set_audio_monitor`` / ``show`` / ``hide`` / ``destroy``.
"""

import logging
import math
import time
from typing import Any

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBorderlessWindowMask,
    NSColor,
    NSMakeRect,
    NSScreen,
    NSTimer,
    NSView,
    NSWindow,
    NSWindowCollectionBehavior,
)

logger = logging.getLogger(__name__)

# Layout (points)
PILL_WIDTH = 168.0
PILL_HEIGHT = 52.0
BAR_COUNT = 11
BAR_WIDTH = 5.0
BAR_GAP = 6.0
BAR_MIN_HEIGHT = 5.0
BAR_MAX_HEIGHT = 30.0
BOTTOM_MARGIN = 90.0  # distance from the bottom of the screen
FPS = 30.0


class WaveformView(NSView):
    """NSView drawing an audio-reactive bar waveform inside a rounded pill."""

    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._level = 0.0
        self._target_level = 0.0
        self._phase = 0.0
        self._last_frame_time = 0.0
        self._audio_monitor = None
        self._anim_timer = None
        return self

    # -- public API --

    def set_audio_monitor(self, monitor: Any) -> None:
        self._audio_monitor = monitor

    def start_animation(self) -> None:
        if self._anim_timer is not None:
            return
        self._last_frame_time = time.monotonic()
        self._anim_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / FPS, self, b"tick:", None, True
        )

    def stop_animation(self) -> None:
        if self._anim_timer is not None:
            self._anim_timer.invalidate()
            self._anim_timer = None

    # -- animation tick --

    def tick_(self, _timer) -> None:
        now = time.monotonic()
        dt = now - self._last_frame_time if self._last_frame_time else 1.0 / FPS
        self._last_frame_time = now

        if self._audio_monitor is not None:
            try:
                self._target_level = max(0.0, min(1.0, self._audio_monitor.get_level()))
            except Exception:
                self._target_level = 0.0

        # Smooth toward the target level
        self._level += (self._target_level - self._level) * min(dt * 8.0, 1.0)
        self._phase += dt * 6.0
        self.setNeedsDisplay_(True)

    # -- drawing --

    def drawRect_(self, _rect) -> None:
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height

        # Rounded "pill" background
        radius = h / 2.0
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, radius, radius)
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.07, 0.07, 0.09, 0.92).set()
        pill.fill()

        # Bars, centered horizontally and vertically
        total_w = BAR_COUNT * BAR_WIDTH + (BAR_COUNT - 1) * BAR_GAP
        start_x = (w - total_w) / 2.0
        mid_y = h / 2.0

        for i in range(BAR_COUNT):
            # Symmetric envelope (taller in the middle) + per-bar animated wobble
            envelope = 1.0 - abs(i - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
            envelope = 0.45 + 0.55 * envelope
            wobble = 0.5 + 0.5 * math.sin(self._phase + i * 0.9)
            amount = self._level * envelope * (0.5 + 0.5 * wobble)
            bar_h = BAR_MIN_HEIGHT + (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT) * amount

            x = start_x + i * (BAR_WIDTH + BAR_GAP)
            y = mid_y - bar_h / 2.0
            bar_rect = NSMakeRect(x, y, BAR_WIDTH, bar_h)
            bar = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bar_rect, BAR_WIDTH / 2.0, BAR_WIDTH / 2.0)
            # Brand-ish purple that brightens with level
            NSColor.colorWithSRGBRed_green_blue_alpha_(
                0.65 + 0.25 * self._level,
                0.55 + 0.20 * self._level,
                0.95,
                0.95,
            ).set()
            bar.fill()


class WaveformWindow:
    """Floating, click-through pill window hosting :class:`WaveformView`."""

    def __init__(self) -> None:
        self._window: NSWindow | None = None
        self._view: WaveformView | None = None
        self._audio_monitor: Any = None
        self._initialized = False

    def set_audio_monitor(self, monitor: Any) -> None:
        self._audio_monitor = monitor
        if self._view is not None:
            self._view.set_audio_monitor(monitor)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        frame = NSMakeRect(0, 0, PILL_WIDTH, PILL_HEIGHT)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSBorderlessWindowMask, NSBackingStoreBuffered, False
        )
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHasShadow_(True)
        window.setIgnoresMouseEvents_(True)
        window.setMovable_(False)
        # Above the menu bar and visible across spaces / fullscreen
        window.setLevel_(101)
        window.setCollectionBehavior_(
            NSWindowCollectionBehavior.canJoinAllSpaces
            | NSWindowCollectionBehavior.stationary
            | NSWindowCollectionBehavior.ignoresCycle
        )

        view = WaveformView.alloc().initWithFrame_(frame)
        if self._audio_monitor is not None:
            view.set_audio_monitor(self._audio_monitor)
        window.setContentView_(view)

        self._window = window
        self._view = view
        self._initialized = True

    def show(self) -> None:
        self._ensure_initialized()
        if self._window is None or self._view is None:
            logger.warning("[waveform] window not initialized, cannot show")
            return

        screen = NSScreen.mainScreen()
        if screen is None:
            logger.warning("[waveform] no main screen")
            return
        vf = screen.visibleFrame()
        x = vf.origin.x + (vf.size.width - PILL_WIDTH) / 2.0
        y = vf.origin.y + BOTTOM_MARGIN
        self._window.setFrameOrigin_((x, y))

        self._window.orderFrontRegardless()
        self._view.start_animation()

    def hide(self) -> None:
        if self._view is not None:
            self._view.stop_animation()
        if self._window is not None:
            self._window.orderOut_(None)

    def destroy(self) -> None:
        if self._view is not None:
            self._view.stop_animation()
            self._view.set_audio_monitor(None)
        if self._window is not None:
            self._window.orderOut_(None)
            self._window.close()
        self._window = None
        self._view = None
        self._initialized = False

"""Lightweight floating indicator window for Whispy state visualization.

Displays a small colored dot with emoji. Uses a high window level to stay
visible above the menu bar and all other windows, including in fullscreen mode.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from AppKit import (
    NSApplication,
    NSBorderlessWindowMask,
    NSColor,
    NSFont,
    NSMakeRect,
    NSPopUpMenuWindowLevel,
    NSScreen,
    NSTextField,
    NSWindow,
    NSWindowCollectionBehavior,
)
from AppKit import NSBackingStoreBuffered as NSBackingStoreType


# Emoji states for each mode
_STATE_EMOJIS = {
    "idle": "\U0001f3a4",
    "listening": "\U000025cf",
    "recording": "\U0001f534",
    "transcribing": "\u23f3",
}

_STATE_COLORS = {
    "idle": (0.5, 0.5, 0.5),
    "listening": (0.2, 0.8, 0.2),
    "recording": (1.0, 0.2, 0.2),
    "transcribing": (0.3, 0.6, 1.0),
}


class IndicatorWindow:
    """Small floating indicator, always visible above all windows."""

    WINDOW_WIDTH = 36
    WINDOW_HEIGHT = 36
    FONT_SIZE = 18.0

    def __init__(self) -> None:
        self._window: Optional[NSWindow] = None
        self._label: Optional[NSTextField] = None
        self._current_state: str = "idle"
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Create the window and label if not already done."""
        if self._initialized:
            return

        # Create label with emoji text
        self._label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        )
        self._label.setBezeled_(False)
        self._label.setDrawsBackground_(False)
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setAlignment_(NSTextField.alignmentCenter())
        self._label.setFont_(NSFont.systemFontOfSize_(self.FONT_SIZE))
        self._label.setStringValue_(_STATE_EMOJIS["idle"])

        # Create borderless window
        window_frame = NSMakeRect(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        window = NSWindow.alloc()
        window.initWithContentRect_styleMask_backing_defer_(
            window_frame,
            NSBorderlessWindowMask,
            NSBackingStoreType,
            False,
        )
        window.setContentView_(self._label)
        # CRITICAL: Must be ABOVE NSStatusWindowLevel (103) to appear
        # above the menu bar. NSPopUpMenuWindowLevel + 1 = 105.
        window.setLevel(NSPopUpMenuWindowLevel + 1)
        window.setCollectionBehavior_(
            NSWindowCollectionBehavior.canJoinAllSpaces
            | NSWindowCollectionBehavior.stationary
            | NSWindowCollectionBehavior.ignoresCycle
        )
        window.setMovableByWindow_(False)
        window.setMovable_(False)
        window.setHasShadow_(False)
        window.setOpaque_(False)
        window.setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.0)
        )
        window.setIgnoresMouseEvents_(True)

        self._window = window
        self._initialized = True

    def show(self, state: str = "listening") -> None:
        """Show the indicator window with the given state."""
        logger.info(f"[indicator] show called with state={state}")
        self._ensure_initialized()
        if not self._window or not self._label:
            logger.warning("[indicator] Window or label is None")
            return

        # Update emoji and color
        emoji = _STATE_EMOJIS.get(state, "\U0001f3a4")
        self._current_state = state
        self._label.setStringValue_(emoji)
        logger.info(f"[indicator] Emoji set to: {emoji}")

        # Set text color based on state
        r, g, b = _STATE_COLORS.get(state, (0.5, 0.5, 0.5))
        self._label.setTextColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
        )

        # Position: top-right corner, below menu bar, visible in fullscreen
        screen = NSApplication.sharedApplication().screens()[0]
        screen_frame = screen.frame()
        # Top-right corner, 16px from edges, below menu bar (24px)
        x = screen_frame.size.width - self.WINDOW_WIDTH - 16 + screen_frame.origin.x
        y = screen_frame.size.height - 24 - self.WINDOW_HEIGHT + 4
        self._window.setFrame_display_(NSMakeRect(x, y, self.WINDOW_WIDTH, self.WINDOW_HEIGHT), True)
        logger.info(f"[indicator] Window positioned at ({x:.0f}, {y:.0f}, {self.WINDOW_WIDTH}, {self.WINDOW_HEIGHT})")

        # Force to front regardless of key window status
        self._window.orderFrontRegardless_()
        logger.info("[indicator] Window ordered front")

    def hide(self) -> None:
        """Hide the indicator window."""
        if self._window:
            self._window.orderOut_(None)

    def destroy(self) -> None:
        """Destroy the window and clean up."""
        if self._window:
            self._window.orderOut_(None)
            self._window.close()
        self._window = None
        self._label = None
        self._initialized = False

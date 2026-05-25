"""Borderless floating window for the ferrofluid visualization.

Creates an NSWindow that stays above regular windows, ignores mouse events
(click-through), and centers on the primary display.
"""

import logging
from typing import Any, Optional

from AppKit import (
    NSApplication,
    NSBorderlessWindowMask,
    NSColor,
    NSFloatingWindowLevel,
    NSPopUpMenuWindowLevel,
    NSView,
    NSWindow,
    NSWindowCollectionBehavior,
)
from AppKit import NSBackingStoreBuffered as NSBackingStoreType

from .ferrofluid_view import FerrofluidView

logger = logging.getLogger(__name__)


class FerrofluidWindow:
    """Manages the floating ferrofluid visualization window."""

    WINDOW_SIZE = 220
    MIN_SIZE = 180

    def __init__(self) -> None:
        self._window: Optional[NSWindow] = None
        self._view: Optional[FerrofluidView] = None
        self._audio_level_monitor: Any = None
        self._initialized = False

    def set_audio_monitor(self, monitor: Any) -> None:
        """Set the audio level monitor to drive the visualization."""
        self._audio_level_monitor = monitor

    def _ensure_initialized(self) -> None:
        """Create the window and view if not already done."""
        if self._initialized:
            return

        # Create the ferrofluid view
        frame = (0, 0, self.WINDOW_SIZE, self.WINDOW_SIZE)
        view = FerrofluidView.alloc().initWithFrame_(frame)
        self._view = view

        # Create borderless window
        window_frame = (0, 0, self.WINDOW_SIZE, self.WINDOW_SIZE)
        style_mask = NSBorderlessWindowMask

        # Use a regular window level but set the window level explicitly
        window = NSWindow.alloc()
        window.initWithContentRect_styleMask_backing_defer_(
            window_frame,
            style_mask,
            NSBackingStoreType,
            False,
        )
        self._window = window

        # Set window level to stay above menu bar and all other windows
        self._window.setLevel(NSPopUpMenuWindowLevel + 2)

        # Collection behavior: don't appear in Mission Control/Spaces
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehavior.canJoinAllSpaces
            | NSWindowCollectionBehavior.stationary
            | NSWindowCollectionBehavior.ignoresCycle
        )

        # Window can't be minimized or resized
        self._window.setMovableByWindow_(False)
        self._window.setMovable_(False)
        self._window.setHasShadow_(True)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.0))

        # Pass audio monitor to the view
        if self._audio_level_monitor is not None:
            view.set_audio_monitor(self._audio_level_monitor)

        # Set the view
        self._window.contentView().addSubview_(view)

        # Ignore mouse events - click-through
        self._window.setIgnoresMouseEvents_(True)

        self._initialized = True

    def show(self) -> None:
        """Show the visualization window and start animation."""
        self._ensure_initialized()
        if self._window is None or self._view is None:
            logger.warning("[ferrofluid] Window or view is None, cannot show")
            return

        # Center on primary display
        screen = NSApplication.sharedApplication().mainScreen()
        if screen is None:
            logger.warning("[ferrofluid] No main screen found")
            return

        screen_frame = screen.visibleFrame()
        win_w = self.WINDOW_SIZE
        win_h = self.WINDOW_SIZE
        # Position: centered horizontally, just below menu bar
        x = (screen_frame.size.width - win_w) / 2 + screen_frame.origin.x
        y = screen_frame.origin.y + screen_frame.size.height - win_h + 28
        self._window.setFrame_display_(
            (x, y, win_w, win_h),
            True,
        )
        logger.info(
            "[ferrofluid] Window positioned at (%.0f, %.0f, %.0f, %.0f)",
            x, y, win_w, win_h,
        )

        # Make window visible BEFORE setting view state
        # Use orderFrontRegardless to bypass key window requirements
        self._window.orderFrontRegardless_()
        logger.info("[ferrofluid] Window ordered front")

        # Make view fully visible immediately (no fade delay)
        self._view._current_fade = 1.0
        self._view._fade_target = 1.0
        self._view.set_audio_level(0.0)

        # Force immediate redraw now that window is visible
        self._window.contentView().setNeedsDisplay_(True)
        logger.info("[ferrofluid] View marked for redraw")

        # Start animation loop
        self._view.start_animation()
        logger.info("[ferrofluid] Animation started")

    def hide(self) -> None:
        """Hide the visualization window and stop animation."""
        if self._view is not None:
            self._view.set_visible(False)
            # Stop animation after fade completes
            from AppKit import NSApp

            NSApp().performSelector(
                self._view.stop_animation,
                withObject=None,
                afterDelay=0.5,
            )

        if self._window is not None:
            self._window.orderOut_(None)

    def destroy(self) -> None:
        """Destroy the window and clean up resources."""
        if self._view is not None:
            self._view.set_visible(False)
            self._view.stop_animation()
        if self._window is not None:
            self._window.orderOut_(None)
            self._window.close()
        self._window = None
        self._view = None
        self._initialized = False

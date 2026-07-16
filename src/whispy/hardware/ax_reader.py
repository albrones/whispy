"""Read the focused text field via macOS Accessibility API.

Used by the correction-detection system to snapshot what the user sees
after Whispy injects text, and to re-read the field on the next trigger
press so edits (corrections) can be detected.
"""

import logging
from dataclasses import dataclass, field
from time import monotonic

logger = logging.getLogger(__name__)


@dataclass
class InjectionSnapshot:
    """What Whispy injected and where, for correction detection on next trigger."""

    app_pid: int
    injected_text: str
    timestamp: float = field(default_factory=monotonic)


def get_frontmost_pid() -> int | None:
    """PID of the frontmost application, or None."""
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.processIdentifier() if app else None
    except Exception:
        return None


def read_focused_field() -> str | None:
    """Read AXValue of the currently focused UI element.

    Returns the text content of the focused field, or None when the element
    is inaccessible, has no AXValue (e.g. a canvas), or when
    ApplicationServices is unavailable.
    """
    try:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateSystemWide,
        )
    except ImportError:
        return None

    try:
        system = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(system, "AXFocusedUIElement", None)
        if err or focused is None:
            return None
        err, value = AXUIElementCopyAttributeValue(focused, "AXValue", None)
        if err or value is None:
            return None
        return str(value)
    except Exception as exc:
        logger.debug("[ax_reader] %s", exc)
        return None

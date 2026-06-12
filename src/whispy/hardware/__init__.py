"""Hardware module."""

from .event_tap import (
    DEFAULT_TRIGGER_KEYCODE,
    QUARTZ_AVAILABLE,
    EventTapListener,
)
from .injection import TextInjector

__all__ = [
    "EventTapListener",
    "TextInjector",
    "QUARTZ_AVAILABLE",
    "DEFAULT_TRIGGER_KEYCODE",
]

"""Platform abstraction: ports and the runtime adapter factory."""

from .detect import PlatformAdapters, detect

__all__ = ["detect", "PlatformAdapters"]

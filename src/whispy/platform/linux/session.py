"""X11 / Wayland session detection for Linux.

Under X11 Whispy grabs the trigger key itself (pynput) and types with xdotool.
Under Wayland a client cannot grab a global key, so the compositor's own key
binding drives the HTTP API (``POST /start`` / ``POST /stop``) and the text is
typed with ``wtype``. These helpers are pure functions of the session
environment so they are unit-testable with env vars patched.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

WAYLAND_MESSAGE = (
    "[whispy] Wayland session detected: the trigger key is your compositor's "
    "binding (it calls POST /start and POST /stop, e.g. Omarchy's "
    "omarchy-dictation-whispy); text is typed with wtype."
)


def is_wayland_session(env: dict[str, str] | None = None) -> bool:
    """Return True when the environment looks like a Wayland session.

    Detected via ``XDG_SESSION_TYPE == 'wayland'`` or the presence of
    ``WAYLAND_DISPLAY``.
    """
    import os

    e = env if env is not None else os.environ
    if e.get("XDG_SESSION_TYPE", "").strip().lower() == "wayland":
        return True
    if e.get("WAYLAND_DISPLAY", "").strip():
        return True
    return False


def announce_wayland_mode(env: dict[str, str] | None = None) -> bool:
    """Log how Whispy is driven on a Wayland session. Returns True if logged."""
    if is_wayland_session(env):
        logger.info(WAYLAND_MESSAGE)
        return True
    return False

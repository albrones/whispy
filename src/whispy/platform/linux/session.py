"""X11 / Wayland session detection for Linux.

Whispy v1 requires an X11 session: global hotkey grab and synthetic input are
restricted under Wayland's security model. These helpers are pure functions of
the session environment so they are unit-testable with env vars patched.
"""

from __future__ import annotations

import sys

WAYLAND_MESSAGE = (
    "[whispy] Wayland session detected. Whispy v1 requires an X11 session — "
    "global hotkeys and text injection do not work under Wayland yet. "
    "Log out and choose an 'Xorg'/'X11' session at your display manager, "
    "then start Whispy again."
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


def warn_if_wayland(env: dict[str, str] | None = None) -> bool:
    """Emit the X11-required message on a Wayland session. Returns True if warned."""
    if is_wayland_session(env):
        print(WAYLAND_MESSAGE, file=sys.stderr)
        return True
    return False

"""Linux/X11 global hotkey listener via pynput.

Listens for the configured trigger key globally under an X11 session and emits
press/release callbacks to the engine. Key repeat while the key is held is
debounced to a single press until release. If the global listener cannot be
established, it degrades with an actionable stderr hint rather than crashing the
daemon.
"""

import sys
from collections.abc import Callable

from ...hardware.event_decode import decode_key_match
from .session import is_wayland_session, warn_if_wayland

_LISTEN_FAILURE_HINT = (
    "[whispy] Could not start the global key listener (pynput).\n"
    "  Whispy v1 requires an X11 session; global hotkeys are unavailable under "
    "Wayland.\n  Trigger-key detection is disabled for this run."
)


def pynput_key_name(key) -> str | None:
    """Normalize a pynput key event to a trigger name.

    Special keys (``Key.ctrl_r`` -> ``"ctrl_r"``) use their enum name; character
    keys (``KeyCode(char='a')``) use the character. Returns None when neither is
    available.
    """
    # Special keys expose a ``.name`` via the Key enum member.
    name = getattr(key, "name", None)
    if name:
        return name
    char = getattr(key, "char", None)
    if char:
        return char
    return None


class PynputHotkeyListener:
    """Global trigger-key listener backed by ``pynput`` (X11 backend)."""

    def __init__(
        self,
        trigger_key: str,
        on_trigger_press: Callable | None = None,
        on_trigger_release: Callable | None = None,
    ) -> None:
        self._trigger_key = trigger_key
        self._on_trigger_press = on_trigger_press
        self._on_trigger_release = on_trigger_release
        self._listener = None
        self._held = False
        self.active = False

    def _on_press(self, key) -> None:
        action = decode_key_match("key_down", pynput_key_name(key), self._trigger_key)
        if action == "press" and not self._held:
            # Debounce auto-repeat: only the first press while held counts.
            self._held = True
            if self._on_trigger_press:
                self._on_trigger_press()

    def _on_release(self, key) -> None:
        action = decode_key_match("key_up", pynput_key_name(key), self._trigger_key)
        if action == "release":
            self._held = False
            if self._on_trigger_release:
                self._on_trigger_release()

    def start(self) -> None:
        """Start the pynput listener thread; degrade gracefully on failure."""
        # Reset the held-key debounce so a previously missed release (e.g. focus
        # loss while held) does not permanently swallow the next press.
        self._held = False

        # Under Wayland pynput typically starts but receives no events; warn up
        # front rather than only on an exception, so the user gets guidance.
        if is_wayland_session():
            warn_if_wayland()

        try:
            from pynput import keyboard
        except Exception as exc:
            print(f"{_LISTEN_FAILURE_HINT}\n  ({exc})", file=sys.stderr)
            return

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.start()
        except Exception as exc:
            print(f"{_LISTEN_FAILURE_HINT}\n  ({exc})", file=sys.stderr)
            self._listener = None
            return

        self.active = True
        print(f"[hotkey] Trigger key listener active (key: {self._trigger_key})")

    def stop(self) -> None:
        """Stop the pynput listener."""
        self.active = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

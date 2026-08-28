"""Linux/X11 global hotkey listener via pynput.

Listens for the configured trigger key globally under an X11 session and emits
press/release callbacks to the engine. Key repeat while the key is held is
debounced to a single press until release. If the global listener cannot be
established, it degrades with an actionable stderr hint rather than crashing the
daemon.
"""

import sys
from collections.abc import Callable

from ...hardware.event_decode import canonical_modifier, decode_key_match
from .session import is_wayland_session, warn_if_wayland

_LISTEN_FAILURE_HINT = (
    "[whispy] Could not start the global key listener (pynput).\n"
    "  Whispy v1 requires an X11 session; global hotkeys are unavailable under "
    "Wayland.\n  Trigger-key detection is disabled for this run."
)

# Same canonical order as event_decode._MODIFIER_ORDER, duplicated here (rather
# than imported) because that tuple is a private implementation detail of the
# macOS mask-based parser — this module only needs the token set, and staying
# independent keeps this a pure string split with no macOS-keycode coupling.
_MODIFIER_TOKENS = frozenset({"ctrl", "alt", "cmd", "shift"})


def split_trigger_combination(value: str) -> tuple[str, frozenset[str]] | None:
    """Split a canonical combination string into ``(key_name, modifier_names)``.

    Unlike ``event_decode.parse_trigger``, this returns the *name* of the final
    key segment rather than resolving it to a macOS keycode — pynput identifies
    keys by name, and a macOS keycode is meaningless on Linux. Modifier tokens
    are validated against the same canonical set ``parse_trigger`` uses, but
    order is not enforced here: this helper only needs to recognize the
    modifier tokens Whispy itself writes to config (via the trigger presets),
    not to define a second canonical spelling.

    Returns ``None`` for a non-string, empty, or trailing-"+" value (no key
    segment), or when a modifier token repeats. A plain key name (no "+") is
    valid and yields an empty modifier set — the caller then behaves exactly
    as it did before combination triggers existed.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    parts = value.split("+")
    key_name = parts[-1]
    if not key_name:
        return None
    modifier_tokens = parts[:-1]
    if len(modifier_tokens) != len(set(modifier_tokens)):
        return None  # a modifier repeated (e.g. "ctrl+ctrl+e")
    if not all(token in _MODIFIER_TOKENS for token in modifier_tokens):
        return None  # unknown modifier token
    return key_name, frozenset(modifier_tokens)


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
        # ``trigger_key`` may be a plain pynput key name (today's behavior) or a
        # combination string (e.g. "ctrl+alt+cmd+e") from a trigger preset.
        # Resolve it once here via the pure split helper above — NOT
        # event_decode.parse_trigger, which resolves to a macOS keycode that is
        # meaningless on this platform. An unparseable value falls back to
        # using it as-is, matching today's behavior (it simply won't match any
        # real key name, same as before this parsing existed).
        split = split_trigger_combination(trigger_key)
        if split is None:
            self._trigger_key = trigger_key
            self._required_modifiers: frozenset[str] = frozenset()
        else:
            self._trigger_key, self._required_modifiers = split
        self._on_trigger_press = on_trigger_press
        self._on_trigger_release = on_trigger_release
        self._listener = None
        self._held = False
        # Canonical modifier names (see event_decode.canonical_modifier)
        # currently held down, tracked so a combination trigger's required
        # modifiers can be checked at the moment the final key is pressed.
        self._held_modifiers: frozenset[str] = frozenset()
        self.active = False

    def _on_press(self, key) -> None:
        key_name = pynput_key_name(key)
        # A modifier press is never itself a trigger press — just track it —
        # UNLESS this modifier IS the configured (single-key) trigger, e.g. the
        # Linux default "ctrl_r": that key must still reach decode_key_match
        # below to fire a press, exactly as it did before combination triggers
        # existed. Only a modifier that is *not* the trigger key is swallowed
        # into the held set here.
        if key_name is not None and key_name != self._trigger_key:
            modifier = canonical_modifier(key_name)
            if modifier is not None:
                self._held_modifiers = self._held_modifiers | {modifier}
                return
        action = decode_key_match(
            "key_down", key_name, self._trigger_key, self._held_modifiers, self._required_modifiers
        )
        if action == "press" and not self._held:
            # Debounce auto-repeat: only the first press while held counts.
            self._held = True
            if self._on_trigger_press:
                self._on_trigger_press()

    def _on_release(self, key) -> None:
        key_name = pynput_key_name(key)
        if key_name is not None and key_name != self._trigger_key:
            modifier = canonical_modifier(key_name)
            if modifier is not None:
                self._held_modifiers = self._held_modifiers - {modifier}
                return
        action = decode_key_match("key_up", key_name, self._trigger_key, self._held_modifiers, self._required_modifiers)
        if action == "release":
            self._held = False
            if self._on_trigger_release:
                self._on_trigger_release()

    def start(self) -> None:
        """Start the pynput listener thread; degrade gracefully on failure."""
        # Reset the held-key debounce so a previously missed release (e.g. focus
        # loss while held) does not permanently swallow the next press. Clear
        # the held-modifiers set for the same reason: a modifier release missed
        # while unfocused must not poison the next combination press.
        self._held = False
        self._held_modifiers = frozenset()

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

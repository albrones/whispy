"""Linux/X11 text injection via xdotool.

Mirrors the macOS injector contract: ``copy_to_clipboard`` selects clipboard
paste vs direct keystroke synthesis, empty text is a no-op, and injection runs
off the calling thread. At construction it probes for the ``xdotool`` binary and
emits an actionable install hint if it is missing, rather than failing silently
at injection time.
"""

import shutil
import subprocess
import sys
import threading

_XDOTOOL_MISSING_HINT = (
    "[whispy] xdotool not found — text injection will not work on Linux/X11.\n"
    "  Install it, e.g.: sudo apt install xdotool  (Debian/Ubuntu)\n"
    "                    sudo dnf install xdotool  (Fedora)\n"
    "                    sudo pacman -S xdotool    (Arch)"
)


class XdotoolInjector:
    """Injects text into the focused X11 window via ``xdotool``."""

    def __init__(self, copy_to_clipboard: bool = False) -> None:
        self._copy_to_clipboard = copy_to_clipboard
        self._xdotool = shutil.which("xdotool")
        if not self._xdotool:
            print(_XDOTOOL_MISSING_HINT, file=sys.stderr)
        # Clipboard mode needs a clipboard setter; prefer xclip, then xsel.
        self._clipboard_cmd = self._resolve_clipboard_cmd()

    @staticmethod
    def _resolve_clipboard_cmd() -> list[str] | None:
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]
        return None

    def update_config(self, copy_to_clipboard: bool) -> None:
        """Update the clipboard copy setting."""
        self._copy_to_clipboard = copy_to_clipboard

    def inject(self, text: str) -> None:
        """Inject transcribed text into the active application."""
        if not text:
            return
        if not self._xdotool:
            # Probed at startup already; stay silent here to avoid log spam.
            return

        # Fall back to keystrokes if clipboard mode is requested but no
        # clipboard setter is installed.
        if self._copy_to_clipboard and self._clipboard_cmd:
            self._inject_via_clipboard(text)
        else:
            self._inject_via_keystrokes(text)

    def _inject_via_clipboard(self, text: str) -> None:
        """Set the X11 clipboard then synthesize Ctrl+V into the focused window."""

        def _run() -> None:
            try:
                setter = subprocess.Popen(
                    self._clipboard_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                setter.communicate(text.encode("utf-8"), timeout=5)
                subprocess.run(
                    [self._xdotool, "key", "--clearmodifiers", "ctrl+v"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _inject_via_keystrokes(self, text: str) -> None:
        """Type the text directly via ``xdotool type``."""

        def _run() -> None:
            try:
                subprocess.run(
                    [self._xdotool, "type", "--clearmodifiers", "--", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass

        threading.Thread(target=_run, daemon=True).start()

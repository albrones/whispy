"""Text injection via macOS accessibility APIs (osascript).

Handles injecting transcribed text into the active application
using clipboard paste or direct keystroke simulation.
"""

import subprocess
import threading
from typing import Optional


class TextInjector:
    """Injects text into the focused application via osascript."""

    def __init__(self, copy_to_clipboard: bool = True) -> None:
        self._copy_to_clipboard = copy_to_clipboard

    def update_config(self, copy_to_clipboard: bool) -> None:
        """Update the clipboard copy setting."""
        self._copy_to_clipboard = copy_to_clipboard

    def inject(self, text: str) -> None:
        """Inject transcribed text into the active application."""
        if not text:
            return

        if self._copy_to_clipboard:
            self._inject_via_clipboard(text)
        else:
            self._inject_via_keystrokes(text)

    def _inject_via_clipboard(self, text: str) -> None:
        """Copy text to clipboard and paste via Cmd+V."""
        escaped = text.replace('"', '\\"')

        def _run() -> None:
            proc = subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'set the clipboard to "{escaped}"',
                    "-e",
                    'tell application "System Events" to keystroke "v" using command down',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        threading.Thread(target=_run, daemon=True).start()

    def _inject_via_keystrokes(self, text: str) -> None:
        """Simulate keystrokes for each character to avoid clipboard interaction."""
        escaped = text.replace('"', '\\"')

        def _run() -> None:
            proc = subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to keystroke "{escaped}"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        threading.Thread(target=_run, daemon=True).start()

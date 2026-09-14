"""Linux/X11 text injection via xdotool.

Mirrors the macOS injector contract: ``copy_to_clipboard`` selects clipboard
paste vs direct keystroke synthesis, empty text is a no-op, and injection runs
off the calling thread. At construction it probes for the ``xdotool`` binary and
emits an actionable install hint if it is missing, rather than failing silently
at injection time. Injections are serialized in call order: each call enqueues
its work and returns immediately, while a single worker thread drains the
queue one job at a time so two overlapping injections never interleave.
"""

import logging
import queue
import shutil
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_XDOTOOL_MISSING_HINT = (
    "[whispy] xdotool not found — text injection will not work on Linux/X11.\n"
    "  Install it, e.g.: sudo apt install xdotool  (Debian/Ubuntu)\n"
    "                    sudo dnf install xdotool  (Fedora)\n"
    "                    sudo pacman -S xdotool    (Arch)"
)


class XdotoolInjector:
    """Injects text into the focused X11 window via ``xdotool``.

    ``inject``/``copy_only`` calls are serialized in call order: each one
    enqueues its subprocess steps and returns immediately, and one worker
    thread drains the queue in FIFO order so overlapping calls never
    interleave their keystrokes.
    """

    def __init__(self, copy_to_clipboard: bool = False) -> None:
        self._copy_to_clipboard = copy_to_clipboard
        self._xdotool = shutil.which("xdotool")
        if not self._xdotool:
            print(_XDOTOOL_MISSING_HINT, file=sys.stderr)
        # Clipboard mode needs a clipboard setter; prefer xclip, then xsel.
        self._clipboard_cmd = self._resolve_clipboard_cmd()
        # FIFO job queue draining into one worker thread, so injections run in
        # call order and never interleave while inject()/copy_only() stay
        # non-blocking.
        self._jobs: queue.Queue = queue.Queue()
        self._worker_lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def _ensure_worker(self) -> None:
        """Start the single FIFO worker thread on first use, if not already running."""
        if self._worker is not None:
            return
        with self._worker_lock:
            if self._worker is None:
                # ponytail: one worker thread per injector, started lazily and
                # never stopped (daemon) -- fine since there is exactly one
                # injector per process.
                self._worker = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                job()
            except Exception:
                logger.exception("[inject] queued job failed")

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

    def copy_only(self, text: str) -> None:
        """Place text on the clipboard without pasting it anywhere.

        Mirrors the macOS injector's contract: used by the recording-limit stop,
        where typing a long transcript into a window that may no longer be
        focused is its own failure mode. A no-op when no clipboard setter is
        installed -- there is nowhere to put the text, and the keystroke fallback
        used by ``inject`` would defeat the purpose.
        """
        if not text or not self._clipboard_cmd:
            return

        def _run() -> None:
            try:
                setter = subprocess.Popen(
                    self._clipboard_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                setter.communicate(text.encode("utf-8"), timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass

        self._ensure_worker()
        self._jobs.put(_run)

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

        self._ensure_worker()
        self._jobs.put(_run)

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

        self._ensure_worker()
        self._jobs.put(_run)

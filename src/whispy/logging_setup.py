"""Daemon logging configuration, including stderr capture.

Extracted from ``whispy_daemon.py`` so the configuration is unit-testable
without importing the entry point (whose module-level side effects would
reconfigure the test session's own logging and stderr).

Deliberately a top-level module rather than one under ``whispy.core``: the
daemon imports it before anything else, and ``whispy.core.__init__`` pulls in
the engine and audio stack. Logging must be configured before that weight is
loaded, so that any diagnostic it emits is already being captured.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3


class StderrCapture:
    """File-like proxy that funnels raw stderr writes into a rotating log file.

    Whispy ships as a GUI ``.app`` with no attached terminal, so anything
    written to ``sys.stderr`` is discarded — including the trigger listener's
    recovery diagnostics and any uncaught thread traceback, which are the
    primary evidence for a dead hotkey.

    A logging handler cannot fix that: handlers receive *log records*, and
    ``print(..., file=sys.stderr)`` never enters the logging system. So the
    capture point has to be the stream itself. Writes are appended through a
    ``RotatingFileHandler`` (rotation stays stdlib's job) and mirrored to the
    original stream, which keeps terminal runs readable and keeps the
    validation harness — which reads the daemon's stderr from its subprocess —
    working unchanged.

    Writes are buffered by line because ``print`` issues the text and its
    newline as separate ``write()`` calls.
    """

    def __init__(self, handler: logging.Handler, mirror=None) -> None:
        self._handler = handler
        self._mirror = mirror
        self._buffer = ""

    @property
    def handler(self) -> logging.Handler:
        """The handler writes go through (its rotation bounds the error log)."""
        return self._handler

    def write(self, text: str) -> int:
        if self._mirror is not None:
            try:
                self._mirror.write(text)
            except Exception:  # pragma: no cover - a broken mirror must not lose the capture
                pass
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(line)
        return len(text)

    def _emit(self, line: str) -> None:
        if not line.strip():
            return
        # A bare record: the text was already formatted by whoever wrote it, so
        # nothing is prefixed on the way through (see the formatter below).
        self._handler.emit(logging.LogRecord("stderr", logging.ERROR, "", 0, "%s", (line,), None))

    def flush(self) -> None:
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""
        if self._mirror is not None:
            try:
                self._mirror.flush()
            except Exception:  # pragma: no cover - defensive
                pass
        self._handler.flush()

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return "utf-8"


def configure_logging(log_path: Path, error_log_path: Path) -> StderrCapture:
    """Configure daemon logging and install the stderr capture. Returns the capture.

    ORDER MATTERS, and it is enforced here rather than left to the call site.
    ``logging.StreamHandler()`` binds ``sys.stderr`` once, at construction.
    Installing the capture first would bind the console handler to it and
    duplicate every INFO log record into the error log, turning it into a
    second copy of the main log. Swapping afterwards leaves the console handler
    on the real stream, so the error log holds only what was written to stderr
    directly.
    """
    # force=True because basicConfig is a silent no-op when the root logger
    # already has handlers. The daemon owns process logging, so a stray earlier
    # basicConfig (from an imported library, or a host embedding the daemon)
    # would otherwise discard this entire configuration without a word — every
    # log line would vanish and nothing would say why.
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
        force=True,
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
            ),
            logging.StreamHandler(),
        ],
    )

    error_handler = logging.handlers.RotatingFileHandler(
        error_log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    error_handler.setFormatter(logging.Formatter("%(message)s"))
    capture = StderrCapture(error_handler, mirror=sys.stderr)
    sys.stderr = capture
    return capture

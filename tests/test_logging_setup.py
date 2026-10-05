"""Daemon logging configuration: stderr capture and its ordering constraint.

Covers the `core-engine` spec requirement that stderr diagnostics are captured
to `~/.whispy-error.log` rather than written to a stream that a GUI `.app`
discards.
"""

import logging
import logging.handlers
import sys

import pytest

from whispy.logging_setup import LOG_BACKUPS, LOG_MAX_BYTES, StderrCapture, configure_logging


@pytest.fixture
def restore_logging():
    """Save and restore global logging state and sys.stderr around a test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_stderr = sys.stderr
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)
    sys.stderr = saved_stderr


class _Mirror:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s
        return len(s)

    def flush(self):
        pass


def _make_capture(tmp_path, mirror=None):
    handler = logging.handlers.RotatingFileHandler(
        tmp_path / "err.log", maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler, StderrCapture(handler, mirror=mirror)


class TestStderrCapture:
    """The wrapper appends written lines to the file and passes them through."""

    def test_written_line_reaches_the_file_and_the_mirror(self, tmp_path):
        mirror = _Mirror()
        handler, capture = _make_capture(tmp_path, mirror)
        capture.write("a diagnostic\n")
        handler.flush()

        assert "a diagnostic" in (tmp_path / "err.log").read_text()
        assert mirror.text == "a diagnostic\n"

    def test_print_writes_text_and_newline_separately(self, tmp_path):
        """print() issues two write() calls — the line must not be split in two."""
        handler, capture = _make_capture(tmp_path)
        print("[event-tap] tap was disabled", file=capture)
        handler.flush()

        contents = (tmp_path / "err.log").read_text()
        assert contents.count("[event-tap] tap was disabled") == 1
        assert contents.strip() == "[event-tap] tap was disabled"

    def test_partial_line_is_held_until_flushed(self, tmp_path):
        handler, capture = _make_capture(tmp_path)
        capture.write("no newline yet")
        handler.flush()
        assert (tmp_path / "err.log").read_text() == ""

        capture.flush()
        assert "no newline yet" in (tmp_path / "err.log").read_text()

    def test_blank_lines_are_not_recorded(self, tmp_path):
        handler, capture = _make_capture(tmp_path)
        capture.write("\n   \n")
        handler.flush()
        assert (tmp_path / "err.log").read_text() == ""

    def test_a_broken_mirror_does_not_lose_the_capture(self, tmp_path):
        class Broken:
            def write(self, s):
                raise OSError("pipe closed")

            def flush(self):
                raise OSError("pipe closed")

        handler, capture = _make_capture(tmp_path, Broken())
        capture.write("still captured\n")
        handler.flush()
        assert "still captured" in (tmp_path / "err.log").read_text()

    def test_non_ascii_survives(self, tmp_path):
        handler, capture = _make_capture(tmp_path)
        capture.write("re-armé — après coup\n")
        handler.flush()
        assert "re-armé — après coup" in (tmp_path / "err.log").read_text()


class TestConfigureLogging:
    """The installed configuration routes stderr and log records to different files."""

    def test_stderr_write_reaches_the_error_log(self, tmp_path, restore_logging):
        log_path = tmp_path / "whispy.log"
        error_log = tmp_path / "whispy-error.log"
        capture = configure_logging(log_path, error_log)

        print("[event-tap] tap was disabled by the OS", file=sys.stderr)
        capture.flush()

        assert "[event-tap] tap was disabled by the OS" in error_log.read_text()

    def test_log_records_do_not_land_in_the_error_log(self, tmp_path, restore_logging):
        """Pins the ordering: the console handler must bind the REAL stderr.

        configure_logging installs the capture after basicConfig. Reversed, the
        StreamHandler would bind the capture and every INFO record would be
        duplicated into the error log, making it a second copy of whispy.log.
        """
        log_path = tmp_path / "whispy.log"
        error_log = tmp_path / "whispy-error.log"
        capture = configure_logging(log_path, error_log)

        logging.getLogger("whispy.test").info("an ordinary log record")
        for handler in logging.getLogger().handlers:
            handler.flush()
        capture.flush()

        assert "an ordinary log record" in log_path.read_text()
        assert "an ordinary log record" not in error_log.read_text()

    def test_the_error_log_is_bounded(self, tmp_path, restore_logging):
        capture = configure_logging(tmp_path / "whispy.log", tmp_path / "whispy-error.log")
        assert isinstance(capture.handler, logging.handlers.RotatingFileHandler)
        assert capture.handler.maxBytes == LOG_MAX_BYTES
        assert capture.handler.backupCount == LOG_BACKUPS

    def test_configuration_applies_even_if_logging_was_already_configured(self, tmp_path, restore_logging):
        """basicConfig is a silent no-op with handlers present; force=True defeats that."""
        logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])

        log_path = tmp_path / "whispy.log"
        configure_logging(log_path, tmp_path / "whispy-error.log")
        logging.getLogger("whispy.test").info("record after a prior basicConfig")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert "record after a prior basicConfig" in log_path.read_text()

    def test_the_main_log_is_still_bounded(self, tmp_path, restore_logging):
        configure_logging(tmp_path / "whispy.log", tmp_path / "whispy-error.log")
        rotating = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert rotating, "the main log handler should rotate"
        assert all(h.maxBytes == LOG_MAX_BYTES and h.backupCount == LOG_BACKUPS for h in rotating)

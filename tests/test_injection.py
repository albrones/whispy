"""Tests for TextInjector with mocked subprocess calls."""

import pytest

from whispy.hardware.injection import TextInjector


# ---------------------------------------------------------------------------
# Clipboard injection mode
# ---------------------------------------------------------------------------


class TestClipboardInjection:
    """Test clipboard-based text injection."""

    def test_clipboard_mode_calls_subprocess(self, mock_subprocess):
        run_mock, popen_mock, popen_instance = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        assert run_mock.called
        call_args = run_mock.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "osascript"
        # Should contain clipboard set command
        assert any("clipboard" in str(arg) for arg in cmd)

    def test_clipboard_uses_keystroke_v(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        call_args = run_mock.call_args
        cmd = call_args[0][0]
        # Second osascript call should paste with cmd+v
        assert any('keystroke "v"' in str(arg) for arg in cmd)


# ---------------------------------------------------------------------------
# Keystroke injection mode
# ---------------------------------------------------------------------------


class TestKeystrokeInjection:
    """Test direct keystroke text injection."""

    def test_keystroke_mode_calls_subprocess(self, mock_subprocess):
        run_mock, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello world")

        assert run_mock.called

    def test_keystroke_mode_contains_text(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello world")

        call_args = run_mock.call_args
        cmd = call_args[0][0]
        assert any("keystroke" in str(arg) for arg in cmd)


# ---------------------------------------------------------------------------
# Empty/None text handling
# ---------------------------------------------------------------------------


class TestEmptyText:
    """Test that empty or None text does not call subprocess."""

    def test_none_text_does_nothing(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject(None)
        assert not run_mock.called

    def test_empty_string_does_nothing(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("")
        assert not run_mock.called

    def test_whitespace_only_calls_subprocess(self, mock_subprocess):
        """Whitespace text is not empty, so it should call subprocess."""
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("   ")
        assert run_mock.called


# ---------------------------------------------------------------------------
# Special character escaping
# ---------------------------------------------------------------------------


class TestSpecialCharacters:
    """Test double quote escaping in osascript commands."""

    def test_double_quotes_escaped_in_clipboard_mode(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject('say "hello"')

        call_args = run_mock.call_args
        cmd = call_args[0][0]
        # The double quote should be escaped
        full_cmd_str = " ".join(str(arg) for arg in cmd)
        assert '\\"hello\\"' in full_cmd_str or '\\"hello\\"' in full_cmd_str

    def test_double_quotes_escaped_in_keystroke_mode(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject('say "hello"')

        call_args = run_mock.call_args
        cmd = call_args[0][0]
        full_cmd_str = " ".join(str(arg) for arg in cmd)
        assert '\\"hello\\"' in full_cmd_str or '\\"hello\\"' in full_cmd_str

    def test_backslashes_handled(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject(r"path\to\file")
        assert run_mock.called

    def test_mixed_special_chars(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject('He said "it\'s fine"')
        assert run_mock.called


# ---------------------------------------------------------------------------
# update_config
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    """Test that update_config changes injection mode."""

    def test_switch_to_clipboard_mode(self):
        injector = TextInjector(copy_to_clipboard=False)
        injector.update_config(copy_to_clipboard=True)
        assert injector._copy_to_clipboard is True

    def test_switch_to_keystroke_mode(self):
        injector = TextInjector(copy_to_clipboard=True)
        injector.update_config(copy_to_clipboard=False)
        assert injector._copy_to_clipboard is False

    def test_initial_clipboard_mode(self):
        injector = TextInjector(copy_to_clipboard=True)
        assert injector._copy_to_clipboard is True

    def test_initial_keystroke_mode(self):
        injector = TextInjector(copy_to_clipboard=False)
        assert injector._copy_to_clipboard is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock

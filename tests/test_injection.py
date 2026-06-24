"""Tests for TextInjector with mocked subprocess calls."""

import sys
from pathlib import Path

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.hardware.injection import TextInjector

# ---------------------------------------------------------------------------
# Clipboard injection mode
# ---------------------------------------------------------------------------


class TestClipboardInjection:
    """Test clipboard-based text injection."""

    def test_clipboard_mode_calls_subprocess(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        assert popen_mock.called
        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "osascript"
        # Should contain clipboard set command
        assert any("clipboard" in str(arg) for arg in cmd)

    def test_clipboard_uses_keystroke_v(self, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        # Second osascript call should paste with cmd+v
        assert any('keystroke "v"' in str(arg) for arg in cmd)


# ---------------------------------------------------------------------------
# Keystroke injection mode
# ---------------------------------------------------------------------------


class TestKeystrokeInjection:
    """Test direct keystroke text injection."""

    def test_keystroke_mode_calls_subprocess(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello world")

        assert popen_mock.called

    def test_keystroke_mode_contains_text(self, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello world")

        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        assert any("keystroke" in str(arg) for arg in cmd)


# ---------------------------------------------------------------------------
# Empty/None text handling
# ---------------------------------------------------------------------------


class TestEmptyText:
    """Test that empty or None text does not call subprocess."""

    def test_none_text_does_nothing(self, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject(None)
        assert not popen_mock.called

    def test_empty_string_does_nothing(self, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("")
        assert not popen_mock.called

    def test_whitespace_only_calls_subprocess(self, mock_subprocess):
        """Whitespace text is not empty, so it should call subprocess."""
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("   ")
        assert popen_mock.called


# ---------------------------------------------------------------------------
# Special character escaping
# ---------------------------------------------------------------------------


class TestSpecialCharacters:
    """Test double quote escaping in osascript commands."""

    def test_double_quotes_escaped_in_clipboard_mode(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject('say "hello"')

        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        # The double quote should be escaped
        full_cmd_str = " ".join(str(arg) for arg in cmd)
        assert '\\"hello\\"' in full_cmd_str or '\\"hello\\"' in full_cmd_str

    def test_double_quotes_escaped_in_keystroke_mode(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject('say "hello"')

        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        full_cmd_str = " ".join(str(arg) for arg in cmd)
        assert '\\"hello\\"' in full_cmd_str or '\\"hello\\"' in full_cmd_str

    def test_backslashes_handled(self, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject(r"path\to\file")
        assert popen_mock.called

    def test_mixed_special_chars(self, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject('He said "it\'s fine"')
        assert popen_mock.called


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
# Keystroke-permission denial detection (osascript error 1002)
# ---------------------------------------------------------------------------

import threading

DENIED_STDERR = (
    b"62:94: execution error: Erreur dans System Events : osascript "
    b"n\xe2\x80\x99est pas autoris\xc3\xa9 \xc3\xa0 envoyer de saisies. (1002)"
)


def _configure_result(popen_instance, returncode, stderr=b""):
    """Make the mocked Popen behave like a finished process."""
    popen_instance.returncode = returncode
    popen_instance.communicate.return_value = (b"", stderr)


def _inject_and_wait(injector, text, *, expect_callback):
    """Inject and wait for the off-thread _spawn worker to fire the callback.

    Returns the list of messages the permission-denied callback received.
    """
    fired = threading.Event()
    messages: list[str] = []

    def _cb(msg):
        messages.append(msg)
        fired.set()

    injector.set_permission_denied_callback(_cb)
    injector.inject(text)
    # Wait for the worker thread; if no callback is expected, the short timeout
    # elapses and we assert emptiness afterwards.
    fired.wait(timeout=2.0 if expect_callback else 0.5)
    return messages


class TestKeystrokeDenialDetection:
    """A denied keystroke (1002) is classified and surfaced via the callback."""

    def test_clipboard_denial_fires_callback(self, mock_subprocess):
        _, _, popen_instance = mock_subprocess
        _configure_result(popen_instance, returncode=1, stderr=DENIED_STDERR)
        injector = TextInjector(copy_to_clipboard=True)
        messages = _inject_and_wait(injector, "hello", expect_callback=True)
        assert len(messages) == 1
        assert "tccutil" in messages[0]

    def test_keystroke_denial_fires_callback(self, mock_subprocess):
        _, _, popen_instance = mock_subprocess
        _configure_result(popen_instance, returncode=1, stderr=DENIED_STDERR)
        injector = TextInjector(copy_to_clipboard=False)
        messages = _inject_and_wait(injector, "hello", expect_callback=True)
        assert len(messages) == 1

    def test_success_does_not_fire_callback(self, mock_subprocess):
        _, _, popen_instance = mock_subprocess
        _configure_result(popen_instance, returncode=0)
        injector = TextInjector(copy_to_clipboard=True)
        messages = _inject_and_wait(injector, "hello", expect_callback=False)
        assert messages == []

    def test_non_1002_failure_does_not_fire_callback(self, mock_subprocess):
        _, _, popen_instance = mock_subprocess
        _configure_result(popen_instance, returncode=1, stderr=b"some other error (1)")
        injector = TextInjector(copy_to_clipboard=True)
        messages = _inject_and_wait(injector, "hello", expect_callback=False)
        assert messages == []


class TestKeystrokeDenialDebounce:
    """Repeated denials surface once per permission-state transition."""

    def test_repeated_denials_fire_once(self, mock_subprocess):
        _, _, popen_instance = mock_subprocess
        _configure_result(popen_instance, returncode=1, stderr=DENIED_STDERR)
        injector = TextInjector(copy_to_clipboard=True)

        calls: list[str] = []
        lock = threading.Lock()

        def _cb(msg):
            with lock:
                calls.append(msg)

        injector.set_permission_denied_callback(_cb)

        for _ in range(3):
            done = threading.Event()
            # Re-wrap so each inject's worker completes before the next.
            injector.inject("hello")
            done.wait(timeout=0.3)

        assert len(calls) == 1  # debounced to a single notification

    def test_success_after_denial_rearms(self, mock_subprocess):
        _, _, popen_instance = mock_subprocess
        injector = TextInjector(copy_to_clipboard=True)
        calls: list[str] = []
        injector.set_permission_denied_callback(lambda m: calls.append(m))

        # Denied
        _configure_result(popen_instance, returncode=1, stderr=DENIED_STDERR)
        injector.inject("a")
        threading.Event().wait(0.3)
        # Recovers
        _configure_result(popen_instance, returncode=0)
        injector.inject("b")
        threading.Event().wait(0.3)
        # Denied again -> should fire a second time
        _configure_result(popen_instance, returncode=1, stderr=DENIED_STDERR)
        injector.inject("c")
        threading.Event().wait(0.3)

        assert len(calls) == 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

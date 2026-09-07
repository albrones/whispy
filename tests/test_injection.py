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

import subprocess
import time

import pytest

from whispy.hardware.injection import _UTF8_ENV, TextInjector


def _ok(popen_instance):
    """Configure the mocked Popen so a full _spawn step sequence completes."""
    popen_instance.returncode = 0
    popen_instance.communicate.return_value = (b"", b"")


def _wait_calls(popen_mock, n, timeout=2.0):
    """Wait until the off-thread worker has issued at least n Popen calls."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if popen_mock.call_count >= n:
            return True
        time.sleep(0.01)
    return popen_mock.call_count >= n


def _commands(popen_mock):
    """Return the list of argv lists passed to each Popen call."""
    return [call.args[0] for call in popen_mock.call_args_list]


def _wait_communicate(popen_instance, n, timeout=2.0):
    """Wait until the off-thread worker has completed at least n communicate() calls.

    Popen(cmd) and the subsequent communicate(input=...) happen as two
    separate calls from the worker thread; waiting only on Popen's call count
    (``_wait_calls``) can observe the nth Popen() before its communicate()
    has run, racing assertions that inspect ``communicate.call_args_list``.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if popen_instance.communicate.call_count >= n:
            return True
        time.sleep(0.01)
    return popen_instance.communicate.call_count >= n


# ---------------------------------------------------------------------------
# Clipboard injection mode
# ---------------------------------------------------------------------------


class TestClipboardInjection:
    """Test clipboard-based text injection (pbcopy stdin + osascript paste)."""

    def test_clipboard_mode_uses_pbcopy_then_paste(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        # Wait for the full sequence (pbcopy, paste, restore) to drain so no
        # background step is left pending (with its restore delay) once this
        # test returns and the subprocess mocks are torn down.
        assert _wait_communicate(popen_instance, 3)
        cmds = _commands(popen_mock)
        # First step copies via pbcopy (text via stdin, never interpolated).
        assert cmds[0] == ["pbcopy"]
        # Second step pastes with a constant Cmd+V AppleScript (no user data).
        assert cmds[1][0] == "osascript"
        assert any('keystroke "v"' in str(arg) for arg in cmds[1])

    def test_clipboard_text_goes_to_pbcopy_stdin(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        assert _wait_communicate(popen_instance, 3)  # pbcopy, paste, restore
        # The text reaches pbcopy (the first step) as stdin bytes, not as an arg.
        assert popen_instance.communicate.call_args_list[0].kwargs.get("input") == b"hello"


# ---------------------------------------------------------------------------
# Clipboard snapshot/restore (privacy: transcript must not linger on the
# pasteboard, and the user's previous clipboard must survive dictation)
# ---------------------------------------------------------------------------


def _ok_pbpaste(run_mock, stdout: bytes = b"") -> None:
    """Configure the mocked subprocess.run (pbpaste snapshot) to succeed."""
    run_mock.return_value.returncode = 0
    run_mock.return_value.stdout = stdout


class TestClipboardRestore:
    """The clipboard is snapshotted before overwrite and restored after paste."""

    def test_snapshot_taken_before_pbcopy(self, mock_subprocess):
        run_mock, _, popen_instance = mock_subprocess
        _ok(popen_instance)
        _ok_pbpaste(run_mock, stdout=b"previous clipboard")
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        # The snapshot is taken synchronously, before the pbcopy/paste/restore
        # sequence is even spawned off-thread, so this call is guaranteed to
        # have happened by the time inject() returns.
        run_mock.assert_called_once()
        assert run_mock.call_args.args[0] == ["pbpaste"]

        # Drain the background sequence before returning: otherwise its
        # pending restore step (after its short delay) could still fire once
        # a later test's subprocess mocks are active, polluting their counts.
        assert _wait_communicate(popen_instance, 3)

    def test_restore_runs_after_paste_with_snapshot_content(self, mock_subprocess):
        run_mock, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        _ok_pbpaste(run_mock, stdout=b"previous clipboard")
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        assert _wait_communicate(popen_instance, 3)  # pbcopy, paste, restore
        cmds = _commands(popen_mock)
        assert cmds[2] == ["pbcopy"]
        assert popen_instance.communicate.call_args_list[2].kwargs.get("input") == b"previous clipboard"

    def test_pbpaste_failure_does_not_break_injection(self, mock_subprocess):
        run_mock, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        run_mock.side_effect = OSError("pbpaste not found")
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        # The transcript still gets copied and pasted despite the snapshot
        # failing; the restore step falls back to an empty snapshot instead
        # of crashing.
        assert _wait_communicate(popen_instance, 3)
        cmds = _commands(popen_mock)
        assert cmds[0] == ["pbcopy"]
        assert popen_instance.communicate.call_args_list[0].kwargs.get("input") == b"hello"
        assert cmds[2] == ["pbcopy"]
        assert popen_instance.communicate.call_args_list[2].kwargs.get("input") == b""


# ---------------------------------------------------------------------------
# Keystroke injection mode
# ---------------------------------------------------------------------------


class TestKeystrokeInjection:
    """Test direct keystroke text injection (text passed via argv)."""

    def test_keystroke_mode_calls_osascript(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello world")

        assert _wait_calls(popen_mock, 1)
        cmd = _commands(popen_mock)[0]
        # Script comes from stdin ("-"); text is the trailing argv argument.
        assert cmd[0] == "osascript"
        assert cmd[1] == "-"
        assert cmd[-1] == "hello world"

    def test_keystroke_script_from_stdin(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello world")

        assert _wait_calls(popen_mock, 1)
        stdin = popen_instance.communicate.call_args.kwargs.get("input")
        assert b"on run argv" in stdin  # text handled as argv, not script source


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


class TestInjectionIsNeverCode:
    """Task 6.5: text with quotes/backslashes/AppleScript metacharacters is
    delivered verbatim and never interpolated into a script (no injection)."""

    # A string that, under the old `osascript -e` interpolation, would break out
    # of the AppleScript string literal and execute attacker code.
    EVIL = 'x" & (do shell script "touch /tmp/pwned") & "\\'

    def test_clipboard_delivers_text_verbatim_via_stdin(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject(self.EVIL)

        assert _wait_communicate(popen_instance, 3)  # pbcopy, paste, restore
        # Exact bytes to pbcopy stdin — no escaping, no shell, no AppleScript.
        assert popen_instance.communicate.call_args_list[0].kwargs.get("input") == self.EVIL.encode("utf-8")
        # No argv anywhere contains an `-e` script carrying the text.
        for cmd in _commands(popen_mock):
            assert "-e" not in cmd or all("do shell script" not in str(a) for a in cmd)

    def test_keystroke_delivers_text_verbatim_via_argv(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject(self.EVIL)

        assert _wait_calls(popen_mock, 1)
        cmd = _commands(popen_mock)[0]
        # The exact text is a single argv element (data), not part of the script.
        assert cmd[-1] == self.EVIL
        assert "-e" not in cmd  # never an inline -e statement built from text

    def test_backslashes_delivered_unmodified(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject(r"path\to\file")

        assert _wait_communicate(popen_instance, 3)  # pbcopy, paste, restore
        assert popen_instance.communicate.call_args_list[0].kwargs.get("input") == rb"path\to\file"


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


# ---------------------------------------------------------------------------
# UTF-8 locale on the clipboard helpers
# ---------------------------------------------------------------------------


def _envs(popen_mock):
    """Return the ``env`` kwarg passed to each Popen call."""
    return [call.kwargs.get("env") for call in popen_mock.call_args_list]


class TestUtf8Locale:
    """pbcopy/pbpaste fall back to Mac Roman without a locale, so every helper
    the injector spawns must carry a forced UTF-8 locale -- snapshot and
    restore included, or fixing the copy alone corrupts the restore."""

    def test_clipboard_path_forces_utf8_locale_on_every_step(self, mock_subprocess):
        run_mock, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        _ok_pbpaste(run_mock, stdout=b"d\xc3\xa9j\xc3\xa0 vu")
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("là créer ça")

        assert _wait_communicate(popen_instance, 3)  # pbcopy, paste, restore
        envs = _envs(popen_mock)
        assert len(envs) == 3
        assert all(env is not None and env["LC_ALL"] == "en_US.UTF-8" for env in envs)
        assert all(env["LANG"] == "en_US.UTF-8" for env in envs)
        # The transcript itself still reaches pbcopy as UTF-8 bytes.
        assert popen_instance.communicate.call_args_list[0].kwargs.get("input") == "là créer ça".encode()

    def test_snapshot_pbpaste_shares_the_locale(self, mock_subprocess):
        run_mock, _, popen_instance = mock_subprocess
        _ok(popen_instance)
        _ok_pbpaste(run_mock, stdout=b"previous")
        injector = TextInjector(copy_to_clipboard=True)
        injector.inject("hello")

        assert run_mock.call_args.args[0] == ["pbpaste"]
        assert run_mock.call_args.kwargs.get("env") is _UTF8_ENV
        assert _wait_communicate(popen_instance, 3)

    def test_keystroke_path_forces_utf8_locale(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=False)
        injector.inject("hello")

        assert _wait_communicate(popen_instance, 1)
        assert _envs(popen_mock) == [_UTF8_ENV]

    def test_copy_only_forces_utf8_locale(self, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        _ok(popen_instance)
        injector = TextInjector(copy_to_clipboard=True)
        injector.copy_only("hello")

        assert _wait_communicate(popen_instance, 1)
        assert _commands(popen_mock) == [["pbcopy"]]
        assert _envs(popen_mock) == [_UTF8_ENV]

    @pytest.mark.macos
    def test_real_pbcopy_pbpaste_roundtrip_with_empty_environment(self):
        """Real seam: with the launchd-like empty environment plus only the
        forced locale, accented text round-trips byte-exact. The developer
        clipboard is snapshotted and restored around the check."""
        if sys.platform != "darwin":
            pytest.skip("pbcopy/pbpaste are macOS-only")
        forced = {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
        sample = "là créer ça".encode()
        saved = subprocess.run(["pbpaste"], capture_output=True, timeout=2, env=forced).stdout
        try:
            subprocess.run(["pbcopy"], input=sample, timeout=2, env=forced, check=True)
            out = subprocess.run(["pbpaste"], capture_output=True, timeout=2, env=forced, check=True).stdout
            assert out == sample
            # Control: the bare environment really does corrupt (documents the bug).
            subprocess.run(["pbcopy"], input=sample, timeout=2, env={}, check=True)
            bare = subprocess.run(["pbpaste"], capture_output=True, timeout=2, env=forced, check=True).stdout
            assert bare != sample
        finally:
            subprocess.run(["pbcopy"], input=saved, timeout=2, env=forced)

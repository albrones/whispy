"""Tests for the `whispy doctor` environment diagnostic."""

import urllib.error

from whispy import doctor
from whispy.doctor import (
    FAIL,
    OK,
    WARN,
    CheckResult,
    check_audio_backend,
    check_daemon,
    check_model,
    check_xdotool,
    run_doctor,
)

_VALID_STATUSES = {OK, WARN, FAIL}


class TestCheckAudioBackend:
    def test_available(self, mocker):
        # Force a successful sounddevice import so the check is independent of
        # whether PortAudio is installed on the host running the tests.
        import sys
        from unittest.mock import MagicMock

        mocker.patch.dict(sys.modules, {"sounddevice": MagicMock()})
        result = check_audio_backend()
        assert result.status == OK
        assert "sounddevice" in result.detail

    def test_unavailable(self, mocker):
        import builtins

        real_import = builtins.__import__

        def _fail(name, *a, **k):
            if name == "sounddevice":
                raise ImportError("no portaudio")
            return real_import(name, *a, **k)

        mocker.patch("builtins.__import__", side_effect=_fail)
        result = check_audio_backend()
        assert result.status == FAIL
        assert "sounddevice" in result.detail


class TestCheckXdotool:
    def test_not_required_off_linux(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "darwin")
        result = check_xdotool()
        assert result.status == OK

    def test_found_on_linux(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch("whispy.doctor.shutil.which", return_value="/usr/bin/xdotool")
        result = check_xdotool()
        assert result.status == OK
        assert "xdotool" in result.detail

    def test_missing_on_linux(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch("whispy.doctor.shutil.which", return_value=None)
        result = check_xdotool()
        assert result.status == FAIL
        assert "xdotool" in result.detail


class TestCheckDaemon:
    def test_running(self, mocker):
        mocker.patch("whispy.doctor.urllib.request.urlopen")
        result = check_daemon(port=9090)
        assert result.status == OK
        assert "9090" in result.detail

    def test_not_running(self, mocker):
        mocker.patch(
            "whispy.doctor.urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        )
        result = check_daemon()
        assert result.status == WARN


class TestCheckModel:
    def test_not_cached(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = check_model()
        assert result.status == WARN
        assert "not downloaded" in result.detail

    def test_cached(self, tmp_path, monkeypatch):
        from whispy.doctor import MODEL_CACHE_GLOB

        monkeypatch.setenv("HOME", str(tmp_path))
        cache = tmp_path / ".cache" / "huggingface" / "hub"
        (cache / MODEL_CACHE_GLOB).mkdir(parents=True)
        result = check_model()
        assert result.status == OK
        assert "parakeet" in result.detail.lower()

    def test_stale_whisper_cache_does_not_count_as_cached(self, tmp_path, monkeypatch):
        """A leftover Whisper snapshot is not the model we now need."""
        monkeypatch.setenv("HOME", str(tmp_path))
        cache = tmp_path / ".cache" / "huggingface" / "hub"
        (cache / "models--Systran--faster-whisper-small").mkdir(parents=True)
        assert check_model().status == WARN


class TestRunDoctor:
    def test_all_ok_returns_0(self, capsys):
        checks = [lambda: CheckResult("a", OK, "fine"), lambda: CheckResult("b", OK, "fine")]
        assert run_doctor(checks=checks) == 0
        assert "All critical checks passed" in capsys.readouterr().out

    def test_failure_returns_1(self, capsys):
        checks = [lambda: CheckResult("a", OK, "fine"), lambda: CheckResult("b", FAIL, "broken")]
        assert run_doctor(checks=checks) == 1
        assert "blocking issue" in capsys.readouterr().out

    def test_warnings_do_not_fail(self, capsys):
        checks = [lambda: CheckResult("a", WARN, "maybe")]
        assert run_doctor(checks=checks) == 0


class TestPermissionChecks:
    def test_all_permission_checks_return_valid_result(self):
        # Quartz/AppKit are mocked in conftest; just verify each check returns a
        # well-formed CheckResult with a known status rather than raising.
        for fn in (
            doctor.check_input_monitoring,
            doctor.check_accessibility,
            doctor.check_microphone,
        ):
            result = fn()
            assert isinstance(result, CheckResult)
            assert result.status in _VALID_STATUSES


class TestDoctorOnLinux:
    """`make doctor` is what a Linux user is told to run when nothing works.

    Every macOS permission check fails at its import on Linux and used to fall
    through to "check System Settings → Privacy & Security", advice for a
    settings app that machine does not have.
    """

    def test_macos_permission_checks_say_nothing_on_linux(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        for fn in (doctor.check_input_monitoring, doctor.check_accessibility, doctor.check_microphone):
            result = fn()
            assert result.status == OK, fn.__name__
            assert "System Settings" not in result.detail, fn.__name__

    def test_wayland_is_reported_as_the_blocker_it_is(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch.dict(doctor.os.environ, {"XDG_SESSION_TYPE": "wayland"}, clear=True)
        result = doctor.check_display()
        assert result.status == FAIL
        assert "Wayland" in result.detail

    def test_a_missing_display_is_reported(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch.dict(doctor.os.environ, {}, clear=True)
        result = doctor.check_display()
        assert result.status == FAIL
        assert "DISPLAY" in result.detail

    def test_an_x11_session_passes(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch.dict(doctor.os.environ, {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11"}, clear=True)
        assert doctor.check_display().status == OK

    def test_a_missing_clipboard_tool_is_a_failure_not_a_footnote(self, mocker):
        # copy_to_clipboard defaults to true, so this is required, not optional.
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch("whispy.doctor.shutil.which", return_value=None)
        result = doctor.check_clipboard_tool()
        assert result.status == FAIL
        assert "xclip" in result.detail

    def test_xsel_satisfies_the_clipboard_check(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch("whispy.doctor.shutil.which", side_effect=lambda b: "/usr/bin/xsel" if b == "xsel" else None)
        assert doctor.check_clipboard_tool().status == OK

    def test_the_daemon_hint_names_the_linux_service(self, mocker):
        mocker.patch("whispy.doctor.sys.platform", "linux")
        mocker.patch("whispy.doctor.urllib.request.urlopen", side_effect=OSError("refused"))
        result = doctor.check_daemon()
        assert "systemctl --user start whispy" in result.detail

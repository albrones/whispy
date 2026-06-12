"""Tests for the `whispy doctor` environment diagnostic."""

import urllib.error

from whispy import doctor
from whispy.doctor import (
    FAIL,
    OK,
    WARN,
    CheckResult,
    check_daemon,
    check_model,
    check_sox,
    run_doctor,
)

_VALID_STATUSES = {OK, WARN, FAIL}


class TestCheckSox:
    def test_found(self, mocker):
        mocker.patch("whispy.doctor.shutil.which", return_value="/opt/homebrew/bin/sox")
        result = check_sox()
        assert result.status == OK
        assert "sox" in result.detail

    def test_not_found(self, mocker):
        mocker.patch("whispy.doctor.shutil.which", return_value=None)
        result = check_sox()
        assert result.status == FAIL
        assert "brew install sox" in result.detail


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
        monkeypatch.setenv("HOME", str(tmp_path))
        cache = tmp_path / ".cache" / "huggingface" / "hub"
        (cache / "models--Systran--faster-whisper-small").mkdir(parents=True)
        result = check_model()
        assert result.status == OK
        assert "small" in result.detail


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

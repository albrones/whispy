"""Tests for the macOS TCC startup probes.

`ensure_automation_access` must validate the real keystroke path, not a benign
query, so it never reports "authorized" when keystrokes are denied (1002).

Every `ensure_*` probe returns its status (True granted / False explicit
denial / None undetermined) so the engine can surface explicit denials in the
UI instead of only logging them.
"""

import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.platform.macos.permissions import (
    ensure_accessibility_access,
    ensure_automation_access,
    ensure_input_monitoring_access,
    ensure_microphone_access,
)


def _run_result(returncode, stderr=""):
    return MagicMock(returncode=returncode, stderr=stderr)


def test_probe_uses_keystroke_not_benign_query(mock_subprocess):
    run_mock, _, _ = mock_subprocess
    run_mock.return_value = _run_result(0)
    ensure_automation_access()

    cmd = run_mock.call_args[0][0]
    joined = " ".join(cmd)
    assert "keystroke" in joined  # exercises the real path
    assert "return name" not in joined  # not the benign query


def test_authorized_when_keystroke_probe_succeeds(mock_subprocess, caplog):
    run_mock, _, _ = mock_subprocess
    run_mock.return_value = _run_result(0)
    with caplog.at_level(logging.INFO):
        ensure_automation_access()
    assert any("authorized" in r.message.lower() for r in caplog.records)


def test_denied_keystroke_reports_not_authorized(mock_subprocess, caplog):
    run_mock, _, _ = mock_subprocess
    # Benign query would have passed, but the keystroke path is denied with 1002.
    run_mock.return_value = _run_result(1, stderr="execution error: ... (1002)")
    with caplog.at_level(logging.WARNING):
        ensure_automation_access()
    text = " ".join(r.message.lower() for r in caplog.records)
    assert "not authorized" in text
    assert "tccutil" in text  # remediation hint present


def test_non_1002_failure_is_unverified_not_authorized(mock_subprocess, caplog):
    run_mock, _, _ = mock_subprocess
    run_mock.return_value = _run_result(1, stderr="some unrelated error (5)")
    with caplog.at_level(logging.WARNING):
        ensure_automation_access()
    text = " ".join(r.message.lower() for r in caplog.records)
    assert "unverified" in text
    assert "authorized." not in text  # must not claim success


class TestProbeReturnValues:
    """Probes report granted/denied/undetermined so the engine can alert."""

    def test_automation_statuses(self, mock_subprocess):
        run_mock, _, _ = mock_subprocess
        run_mock.return_value = _run_result(0)
        assert ensure_automation_access() is True
        run_mock.return_value = _run_result(1, stderr="execution error: ... (1002)")
        assert ensure_automation_access() is False
        run_mock.return_value = _run_result(1, stderr="some unrelated error (5)")
        assert ensure_automation_access() is None
        run_mock.side_effect = OSError("no osascript")
        assert ensure_automation_access() is None

    def _iokit(self, mocker, check_status, request_granted):
        iokit = MagicMock()
        iokit.IOHIDCheckAccess.return_value = check_status
        iokit.IOHIDRequestAccess.return_value = request_granted
        mocker.patch("whispy.platform.macos.permissions.ctypes.CDLL", return_value=iokit)
        return iokit

    def test_input_monitoring_granted(self, mocker):
        self._iokit(mocker, check_status=0, request_granted=False)
        assert ensure_input_monitoring_access() is True

    def test_input_monitoring_prior_denial_is_false(self, mocker):
        self._iokit(mocker, check_status=1, request_granted=False)
        assert ensure_input_monitoring_access() is False

    def test_input_monitoring_not_determined_is_none(self, mocker):
        # System prompt shown, user hasn't answered: not a definitive denial.
        self._iokit(mocker, check_status=2, request_granted=False)
        assert ensure_input_monitoring_access() is None

    def test_input_monitoring_granted_via_request(self, mocker):
        self._iokit(mocker, check_status=2, request_granted=True)
        assert ensure_input_monitoring_access() is True

    def test_input_monitoring_unavailable_is_none(self, mocker):
        mocker.patch("whispy.platform.macos.permissions.ctypes.CDLL", side_effect=OSError("no IOKit"))
        assert ensure_input_monitoring_access() is None

    def _application_services(self, monkeypatch, trusted):
        mod = types.ModuleType("ApplicationServices")
        mod.AXIsProcessTrusted = lambda: trusted
        mod.AXIsProcessTrustedWithOptions = MagicMock(return_value=trusted)
        mod.kAXTrustedCheckOptionPrompt = "AXTrustedCheckOptionPrompt"
        monkeypatch.setitem(sys.modules, "ApplicationServices", mod)
        return mod

    def test_accessibility_trusted(self, monkeypatch):
        self._application_services(monkeypatch, trusted=True)
        assert ensure_accessibility_access() is True

    def test_accessibility_untrusted_is_false_and_prompts(self, monkeypatch):
        mod = self._application_services(monkeypatch, trusted=False)
        assert ensure_accessibility_access() is False
        mod.AXIsProcessTrustedWithOptions.assert_called_once()

    def _avfoundation(self, monkeypatch, status):
        mod = types.ModuleType("AVFoundation")
        mod.AVMediaTypeAudio = "soun"
        device = MagicMock()
        device.authorizationStatusForMediaType_.return_value = status
        mod.AVCaptureDevice = device
        monkeypatch.setitem(sys.modules, "AVFoundation", mod)
        return device

    def test_microphone_granted(self, monkeypatch):
        self._avfoundation(monkeypatch, status=3)
        assert ensure_microphone_access() is True

    def test_microphone_denied_is_false(self, monkeypatch):
        self._avfoundation(monkeypatch, status=2)
        assert ensure_microphone_access() is False

    def test_microphone_not_determined_prompts_and_is_none(self, monkeypatch):
        device = self._avfoundation(monkeypatch, status=0)
        assert ensure_microphone_access() is None
        device.requestAccessForMediaType_completionHandler_.assert_called_once()

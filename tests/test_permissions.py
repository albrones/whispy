"""Tests for the macOS keystroke-authorization startup probe.

`ensure_automation_access` must validate the real keystroke path, not a benign
query, so it never reports "authorized" when keystrokes are denied (1002).
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.platform.macos.permissions import ensure_automation_access


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

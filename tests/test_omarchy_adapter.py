"""The Omarchy dictation adapter never fails silently.

Runs the real script with a fake ``notify-send`` on PATH against a port nothing
listens on: the user must get « Whispy ne répond pas » and a non-zero exit.
"""

import socket
import subprocess
from pathlib import Path

ADAPTER = Path(__file__).parent.parent / "packaging" / "omarchy" / "omarchy-dictation-whispy"


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run(tmp_path: Path, action: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "notifications.log"
    fake = bin_dir / "notify-send"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{log}"\n')
    fake.chmod(0o755)
    token = tmp_path / ".config" / "whispy" / "config.token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("token")
    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "WHISPY_API_URL": f"http://127.0.0.1:{_closed_port()}",
    }
    result = subprocess.run(["bash", str(ADAPTER), action], env=env, capture_output=True, text=True, timeout=20)
    return result, log.read_text() if log.exists() else ""


def test_unreachable_whispy_notifies_and_fails(tmp_path):
    for action in ("start", "stop", "toggle"):
        result, notifications = _run(tmp_path, action)
        assert result.returncode != 0, action
        assert "Whispy ne répond pas" in notifications, action


def test_unknown_action_prints_usage(tmp_path):
    result, notifications = _run(tmp_path, "record")
    assert result.returncode == 1
    assert "Usage" in result.stderr
    assert notifications == ""

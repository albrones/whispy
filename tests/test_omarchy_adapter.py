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


# --- trigger <preset>: the bar panel's trigger picker -------------------------


class _ConfigApi:
    """A stand-in Whispy API that records each POST /config body."""

    def __init__(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        bodies = self.bodies = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                bodies.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')

            def log_message(self, *_args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def _fake(bin_dir: Path, name: str, log: Path, exit_code: int = 0) -> None:
    script = bin_dir / name
    script.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit {exit_code}\n')
    script.chmod(0o755)


def _run_trigger(tmp_path: Path, preset: str, api_url: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "calls.log"
    for name in ("hyprctl", "notify-send", "omarchy-shell"):
        _fake(bin_dir, name, calls)
    backend = bin_dir / "omarchy-default-dictation"
    backend.write_text("#!/bin/sh\necho whispy\n")
    backend.chmod(0o755)
    token = tmp_path / ".config" / "whispy" / "config.token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("token")
    env = {"HOME": str(tmp_path), "PATH": f"{bin_dir}:/usr/bin:/bin", "WHISPY_API_URL": api_url}
    result = subprocess.run(
        ["bash", str(ADAPTER), "trigger", preset], env=env, capture_output=True, text=True, timeout=20
    )
    return result, calls.read_text() if calls.exists() else ""


EXPECTED_BINDINGS = {
    "right_option_hold": ['o.bind_hold("ISO_Level3_Shift"', 'o.bind_hold("Alt_R"'],
    "right_ctrl_hold": ['o.bind_hold("Control_R"'],
    "f9_hold": ['o.bind_hold("F9"'],
    "left_option_space_toggle": ['o.bind("ALT + SPACE", "Toggle dictation", "omarchy-dictation toggle")'],
}


def test_trigger_saves_preset_writes_binding_and_reloads(tmp_path):
    api = _ConfigApi()
    try:
        for preset, bindings in EXPECTED_BINDINGS.items():
            result, calls = _run_trigger(tmp_path, preset, api.url)
            assert result.returncode == 0, result.stderr
            assert api.bodies[-1] == ("/config", {"omarchy_trigger": preset})
            lua = (tmp_path / ".config" / "whispy" / "shortcuts.lua").read_text()
            # Every preset key is freed first, so only the chosen one dictates.
            assert lua.index("hl.unbind(keys)") < lua.index(bindings[0])
            for binding in bindings:
                assert binding in lua, preset
            other = [b for p, bs in EXPECTED_BINDINGS.items() if p != preset for b in bs]
            assert not any(binding in lua for binding in other), preset
            if preset.endswith("_hold"):
                # Hold keys keep reaching apps: AltGr characters stay typable.
                assert lua.count("non_consuming = true") == len(bindings)
            assert calls.splitlines()[-1].startswith("hyprctl reload")
    finally:
        api.close()


def test_trigger_rejects_unknown_preset_without_touching_anything(tmp_path):
    api = _ConfigApi()
    try:
        result, calls = _run_trigger(tmp_path, "caps_lock_hold", api.url)
    finally:
        api.close()
    assert result.returncode == 2
    assert "right_ctrl_hold" in result.stderr
    assert api.bodies == []
    assert not (tmp_path / ".config" / "whispy" / "shortcuts.lua").exists()
    assert "hyprctl" not in calls


def test_trigger_with_whispy_down_keeps_the_old_binding(tmp_path):
    shortcuts = tmp_path / ".config" / "whispy" / "shortcuts.lua"
    shortcuts.parent.mkdir(parents=True)
    shortcuts.write_text("-- previous binding\n")
    result, calls = _run_trigger(tmp_path, "f9_hold", f"http://127.0.0.1:{_closed_port()}")
    assert result.returncode != 0
    assert shortcuts.read_text() == "-- previous binding\n"
    assert "Whispy ne répond pas" in calls
    assert "hyprctl" not in calls


def test_generated_lua_parses(tmp_path):
    """Hyprland would reject a file with a syntax error; luac catches it here."""
    import shutil

    import pytest

    luac = shutil.which("luac")
    if luac is None:
        pytest.skip("luac not installed")
    api = _ConfigApi()
    try:
        for preset in EXPECTED_BINDINGS:
            result, _ = _run_trigger(tmp_path, preset, api.url)
            assert result.returncode == 0, result.stderr
            shortcuts = tmp_path / ".config" / "whispy" / "shortcuts.lua"
            check = subprocess.run([luac, "-p", str(shortcuts)], capture_output=True, text=True)
            assert check.returncode == 0, check.stderr
    finally:
        api.close()

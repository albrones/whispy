"""The Omarchy dictation adapter drives Whispy V2 through its control socket.

Runs the real script with fakes on PATH: ``whispy2`` (the socket client,
``whispy2 send <request>``), ``notify-send``, ``hyprctl`` and ``omarchy-shell``.
A call Whispy does not answer must never be silent: the user gets « Whispy is
not answering » and a non-zero exit.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ADAPTER = Path(__file__).parent.parent / "packaging" / "omarchy" / "omarchy-dictation-whispy"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")


def _fake(bin_dir: Path, name: str, log: Path, body: str = "exit 0") -> None:
    script = bin_dir / name
    script.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n{body}\n')
    script.chmod(0o755)


def _env(tmp_path: Path, whispy2: str | None) -> tuple[dict, Path]:
    """Fakes on PATH; ``whispy2`` is the fake client's body, None for not installed."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "calls.log"
    for name in ("hyprctl", "notify-send", "omarchy-shell"):
        _fake(bin_dir, name, calls)
    backend = bin_dir / "omarchy-default-dictation"
    backend.write_text("#!/bin/sh\necho whispy\n")
    backend.chmod(0o755)
    if whispy2 is not None:
        _fake(bin_dir, "whispy2", calls, whispy2)
    # jq from the system, but no whispy2 found outside the fakes.
    jq_dir = Path(shutil.which("jq") or "/usr/bin/jq").parent
    return {"HOME": str(tmp_path), "PATH": f"{bin_dir}:{jq_dir}:/usr/bin:/bin"}, calls


def _run(tmp_path: Path, *args: str, whispy2: str | None = "echo ok") -> tuple[subprocess.CompletedProcess, str]:
    env, calls = _env(tmp_path, whispy2)
    result = subprocess.run(["bash", str(ADAPTER), *args], env=env, capture_output=True, text=True, timeout=20)
    return result, calls.read_text() if calls.exists() else ""


V2_DOWN = 'echo "whispy2: Whispy V2 is not answering on /x/control.sock (Connection refused)" >&2; exit 2'


def test_each_dictation_key_is_one_request_on_the_socket(tmp_path):
    for action in ("start", "stop", "toggle"):
        result, calls = _run(tmp_path, action)
        assert result.returncode == 0, result.stderr
        assert f"whispy2 send {action}" in calls.splitlines()
    # No V1: no HTTP API, no token, no curl.
    assert "curl" not in ADAPTER.read_text()
    assert "9090" not in ADAPTER.read_text()


def test_unanswered_whispy_notifies_and_fails(tmp_path):
    for action in ("start", "stop", "toggle"):
        result, calls = _run(tmp_path, action, whispy2=V2_DOWN)
        assert result.returncode != 0, action
        assert "Whispy is not answering" in calls, action
        assert "Connection refused" in result.stderr, action


def test_a_refused_start_is_not_silent(tmp_path):
    result, calls = _run(
        tmp_path, "start", whispy2='echo "refused: Whispy V1 is running and holds the trigger"; exit 1'
    )
    assert result.returncode != 0
    assert "Whispy is not answering" in calls
    assert "V1 is running" in result.stderr


def test_missing_whispy2_says_so(tmp_path):
    result, calls = _run(tmp_path, "start", whispy2=None)
    assert result.returncode != 0
    assert "whispy2 is not installed" in result.stderr
    assert "Whispy is not answering" in calls


def test_whispy2_bin_overrides_the_lookup(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    log = tmp_path / "other.log"
    _fake(other, "whispy2", log, "echo ok")
    env, _ = _env(tmp_path, None)
    env["WHISPY2_BIN"] = str(other / "whispy2")
    result = subprocess.run(["bash", str(ADAPTER), "start"], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "whispy2 send start" in log.read_text()


def test_unknown_action_prints_usage(tmp_path):
    result, calls = _run(tmp_path, "record")
    assert result.returncode == 1
    assert "Usage" in result.stderr
    assert "notify-send" not in calls


# --- trigger <preset>: the bar panel's trigger picker -------------------------


EXPECTED_BINDINGS = {
    "right_option_hold": ['o.bind_hold("ISO_Level3_Shift"', 'o.bind_hold("Alt_R"'],
    "right_ctrl_hold": ['o.bind_hold("Control_R"'],
    "f9_hold": ['o.bind_hold("F9"'],
    "left_option_space_toggle": ['o.bind("ALT + SPACE", "Toggle dictation", "omarchy-dictation toggle")'],
}


def _config(tmp_path: Path) -> Path:
    return tmp_path / ".config" / "whispy" / "config.json"


def test_trigger_saves_preset_writes_binding_and_reloads(tmp_path):
    config = _config(tmp_path)
    config.parent.mkdir(parents=True)
    # V1's and V2's other keys survive the change.
    config.write_text(json.dumps({"trigger_mode": "toggle", "copy_to_clipboard": False, "trigger": 61}, indent=2))
    for preset, bindings in EXPECTED_BINDINGS.items():
        result, calls = _run(tmp_path, "trigger", preset)
        assert result.returncode == 0, result.stderr
        saved = json.loads(config.read_text())
        assert saved == {"trigger_mode": "toggle", "copy_to_clipboard": False, "trigger": 61, "omarchy_trigger": preset}
        assert config.stat().st_mode & 0o077 == 0, "the config stays private"
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
    # Changing the key needs no running Whispy: nothing was asked of the socket.
    assert "whispy2" not in calls
    assert list(config.parent.glob("config.json.*")) == [], "no temporary file left behind"


def test_trigger_creates_the_config_when_there_is_none(tmp_path):
    result, _ = _run(tmp_path, "trigger", "f9_hold")
    assert result.returncode == 0, result.stderr
    assert json.loads(_config(tmp_path).read_text()) == {"omarchy_trigger": "f9_hold"}


def test_trigger_rejects_unknown_preset_without_touching_anything(tmp_path):
    result, calls = _run(tmp_path, "trigger", "caps_lock_hold")
    assert result.returncode == 2
    assert "right_ctrl_hold" in result.stderr
    assert not _config(tmp_path).exists()
    assert not (tmp_path / ".config" / "whispy" / "shortcuts.lua").exists()
    assert "hyprctl" not in calls


def test_trigger_with_a_broken_config_keeps_the_old_binding(tmp_path):
    config = _config(tmp_path)
    config.parent.mkdir(parents=True)
    config.write_text("{ not json")
    shortcuts = config.parent / "shortcuts.lua"
    shortcuts.write_text("-- previous binding\n")
    result, calls = _run(tmp_path, "trigger", "f9_hold")
    assert result.returncode != 0
    assert "not valid JSON" in result.stderr
    assert config.read_text() == "{ not json"
    assert shortcuts.read_text() == "-- previous binding\n"
    assert "hyprctl" not in calls
    assert list(config.parent.glob("config.json.*")) == []


def test_generated_lua_parses(tmp_path):
    """Hyprland would reject a file with a syntax error; luac catches it here."""
    luac = shutil.which("luac")
    if luac is None:
        pytest.skip("luac not installed")
    for preset in EXPECTED_BINDINGS:
        result, _ = _run(tmp_path, "trigger", preset)
        assert result.returncode == 0, result.stderr
        shortcuts = tmp_path / ".config" / "whispy" / "shortcuts.lua"
        check = subprocess.run([luac, "-p", str(shortcuts)], capture_output=True, text=True)
        assert check.returncode == 0, check.stderr


def test_shortcuts_reads_back_the_preset_trigger_saved(tmp_path):
    """The installer path: no Whispy, no reload; the saved preset, else the default."""
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    config = _config(tmp_path)
    shortcuts = config.parent / "shortcuts.lua"

    result = subprocess.run(["bash", str(ADAPTER), "shortcuts"], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "right_option_hold"
    assert 'o.bind_hold("ISO_Level3_Shift"' in shortcuts.read_text()

    # Saved by `trigger` (jq's layout), then read back by `shortcuts`.
    assert _run(tmp_path, "trigger", "f9_hold")[0].returncode == 0
    shortcuts.unlink()
    result = subprocess.run(["bash", str(ADAPTER), "shortcuts"], env=env, capture_output=True, text=True, timeout=20)
    assert result.stdout.strip() == "f9_hold"
    assert 'o.bind_hold("F9"' in shortcuts.read_text()

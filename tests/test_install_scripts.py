"""Structural tests for the install scripts (install.sh, scripts/bootstrap.sh).

CI has no clean macOS/Linux box to run these end to end, so we guard the
release-critical invariants as text: the scripts must not gate on sox (the audio
backend is sounddevice/PortAudio now), the one-liner must be safe under
`curl | bash` (no blocking prompt), the chosen WHISPER_MODEL must be persisted so
the detached daemon actually uses it, and install.sh must branch per-OS rather
than writing a macOS LaunchAgent on Linux.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"
BOOTSTRAP = ROOT / "scripts" / "bootstrap.sh"


@pytest.fixture(scope="module")
def install() -> str:
    return INSTALL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bootstrap() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


def test_scripts_exist():
    assert INSTALL.is_file() and BOOTSTRAP.is_file()


def test_install_does_not_gate_on_sox(install: str):
    # The old `command -v sox` gate hard-exited on a clean machine.
    assert "command -v sox" not in install
    assert "brew install sox" not in install


def test_bootstrap_does_not_gate_on_sox(bootstrap: str):
    assert "command -v sox" not in bootstrap
    assert "brew install sox" not in bootstrap


def test_bootstrap_has_no_blocking_prompt(bootstrap: str):
    # A `read -p` prompt defaults to abort under `curl | bash` (no TTY).
    assert "read -r -p" not in bootstrap
    assert "read -p" not in bootstrap


def test_install_persists_whisper_model(install: str):
    # The daemon runs detached and won't inherit WHISPER_MODEL from the shell,
    # so the installer must write it into config.json.
    assert 'if [ -n "${WHISPER_MODEL:-}" ]' in install
    assert '"model_size"' in install
    assert "config.json" in install


def test_install_branches_per_os(install: str):
    # Linux must get a systemd user unit, not a macOS LaunchAgent.
    assert 'OS="$(uname -s)"' in install
    assert 'if [ "$OS" = "Linux" ]' in install
    assert "systemctl --user" in install
    assert "whispy.service" in install

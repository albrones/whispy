"""Structural tests for the install scripts (install.sh, scripts/bootstrap.sh).

CI has no clean macOS/Linux box to run these end to end, so we guard the
release-critical invariants as text: the scripts must not gate on sox (the audio
backend is sounddevice/PortAudio now), the one-liner must be safe under
`curl | bash` (no blocking prompt), the chosen WHISPER_MODEL must be persisted so
the detached daemon actually uses it, and install.sh must branch per-OS rather
than writing a macOS LaunchAgent on Linux.
"""

import re
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


def test_install_uninstall_offers_user_data_removal(install: str):
    # The venv/LaunchAgent/systemd-unit removal leaves behind the config
    # (has the API token), the logs, and the downloaded Whisper model cache
    # (0.5-3 GB) -- uninstall must at least offer to clean those up too.
    assert ".config/whispy" in install
    assert ".whispy.log" in install
    assert "models--Systran--faster-whisper-" in install


def test_install_uninstall_scopes_model_cache_deletion(install: str):
    # The HuggingFace hub cache is shared with other tools (any project using
    # huggingface_hub caches there) -- uninstall must only ever remove the
    # faster-whisper model snapshots, never the whole hub directory.
    assert "models--Systran--faster-whisper-*" in install
    assert 'rm -rf "$HOME/.cache/huggingface/hub"' not in install
    assert "rm -rf $HOME/.cache/huggingface/hub\n" not in install
    assert 'rm -rf "$HOME/.cache/huggingface"' not in install


def test_install_uninstall_data_removal_defaults_to_keep(install: str):
    # Deleting the model cache means a reinstall re-downloads 0.5-3 GB, so
    # the default answer must be "no" (keep), not "yes" (remove).
    assert 'REMOVE_DATA="n"' in install
    assert re.search(r"\[y/N\]", install, re.IGNORECASE)


def test_install_uninstall_data_prompt_is_tty_gated(install: str):
    # A `read -p` here must not block a non-interactive run (e.g. bootstrap.sh
    # piping install.sh --uninstall under `curl | bash`, no TTY).
    assert "[ -t 0 ]" in install
    assert "read -r -p" in install


def test_bootstrap_uninstall_delegates_to_install(bootstrap: str):
    # bootstrap.sh must not duplicate the user-data prompt itself (that would
    # risk a second, un-gated blocking read); it delegates to install.sh.
    assert '"$WHISPY_HOME/install.sh" --uninstall' in bootstrap

"""Structural tests for the install scripts (install.sh, scripts/bootstrap.sh)
and the CI workflow's dependency list.

CI has no clean macOS/Linux box to run the install scripts end to end, so we
guard the release-critical invariants as text: nothing may gate on sox and the
default-tier CI jobs may not install it (the audio backend is
sounddevice/PortAudio now, so needing sox would mean the project quietly
reacquired a dependency it removed) -- the real-seam job is exempt, where sox
synthesizes test fixtures rather than serving the application; the one-liner
must be safe under `curl | bash` (no blocking prompt),
uninstall must scope model-cache deletion to Whispy's own snapshot, and
install.sh must branch per-OS rather than writing a macOS LaunchAgent on
Linux.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"
BOOTSTRAP = ROOT / "scripts" / "bootstrap.sh"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def install() -> str:
    return INSTALL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bootstrap() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ci_workflow() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_scripts_exist():
    assert INSTALL.is_file() and BOOTSTRAP.is_file()


def test_install_does_not_gate_on_sox(install: str):
    # The old `command -v sox` gate hard-exited on a clean machine.
    assert "command -v sox" not in install
    assert "brew install sox" not in install


def test_bootstrap_does_not_gate_on_sox(bootstrap: str):
    assert "command -v sox" not in bootstrap
    assert "brew install sox" not in bootstrap


def _ci_job(workflow: str, name: str) -> str:
    """Return one job's block from the workflow text (same text-guard style as the rest)."""
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \w[\w-]*:\n|\Z)", workflow, re.M | re.S)
    assert match, f"job {name!r} not found in ci.yml"
    return match.group(1)


def test_ci_workflow_does_not_gate_on_sox(ci_workflow: str):
    # `command -v sox` was the old runtime gate. sox is not a runtime dependency
    # any more -- the audio backend is sounddevice/PortAudio -- so nothing in CI
    # may treat its absence as a failure.
    assert "command -v sox" not in ci_workflow


@pytest.mark.parametrize("job", ["test", "test-linux"])
def test_default_tier_jobs_do_not_install_sox(ci_workflow: str, job: str):
    """The tiers that stand in for a user's machine must not need sox.

    This is the guard that matters: if the default suite ever depends on sox,
    the project has quietly reacquired a dependency it removed. The real-seam
    job is exempt on purpose (see below) -- sox there synthesizes test fixtures,
    it is not something the application calls.
    """
    assert "brew install sox" not in _ci_job(ci_workflow, job)
    assert "install sox" not in _ci_job(ci_workflow, job)


def test_real_seam_job_installs_sox_and_excludes_the_tts_module(ci_workflow: str):
    """The real-model tier needs sox, and must skip the `say`-dependent module.

    Without sox both real-model modules skip at import and the job silently
    passes on a third of its tests. With it, the deterministic half runs. The
    `say`-based module stays excluded explicitly: its synthesis is not
    byte-stable between runs, so it flakes.
    """
    job = _ci_job(ci_workflow, "test-macos-real-seam")
    assert "brew install sox" in job, "the real-model tests cannot synthesize clips without sox"
    assert "--ignore=tests/test_transcription_quality.py" in job, (
        "the `say`-dependent module must stay out of CI, and explicitly"
    )


def test_bootstrap_has_no_blocking_prompt(bootstrap: str):
    # A `read -p` prompt defaults to abort under `curl | bash` (no TTY).
    assert "read -r -p" not in bootstrap
    assert "read -p" not in bootstrap


def test_install_has_no_model_selection(install: str):
    # There is one model. WHISPER_MODEL selected among Whisper's five size
    # presets; with a single-size backend it selects nothing, so it must not
    # linger as dead surface in the installer.
    assert "WHISPER_MODEL" not in install
    assert "model_size" not in install


def test_bootstrap_has_no_model_selection(bootstrap: str):
    assert "WHISPER_MODEL" not in bootstrap


def test_install_branches_per_os(install: str):
    # Linux must get a systemd user unit, not a macOS LaunchAgent.
    assert 'OS="$(uname -s)"' in install
    assert 'if [ "$OS" = "Linux" ]' in install
    assert "systemctl --user" in install
    assert "whispy.service" in install


def test_install_uninstall_offers_user_data_removal(install: str):
    # The venv/LaunchAgent/systemd-unit removal leaves behind the config
    # (has the API token), the logs, and the downloaded model cache (639 MB)
    # -- uninstall must at least offer to clean those up too.
    assert ".config/whispy" in install
    assert ".whispy.log" in install
    assert "models--istupakov--parakeet-tdt-0.6b-v3-onnx" in install


def test_uninstall_never_deletes_the_shared_hub_cache(install: str):
    # The hub cache holds other tools' models; only Whispy's snapshot may go.
    assert "rm -rf $MODEL_CACHE_GLOB" in install
    assert 'rm -rf "$HOME/.cache/huggingface/hub"' not in install
    assert "rm -rf $HOME/.cache/huggingface/hub\n" not in install


def test_uninstall_reports_the_stale_whisper_cache_without_deleting_it(install: str):
    # Upgraders keep a 466 MB orphan; name it, do not delete another era's data.
    assert "STALE_WHISPER_GLOB" in install
    assert "models--Systran--faster-whisper-*" in install
    assert "rm -rf $STALE_WHISPER_GLOB" not in install


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

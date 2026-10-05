"""Structural tests for the install scripts (install.sh, scripts/bootstrap.sh)
and the CI workflow's dependency list.

CI has no clean macOS/Linux box to run the install scripts end to end, so we
guard the release-critical invariants as text: the scripts (and the CI
workflow) must not gate on or install sox (the audio backend is
sounddevice/PortAudio now), the one-liner must be safe under `curl | bash`
(no blocking prompt),
uninstall must scope model-cache deletion to Whispy's own snapshot, and
install.sh must branch per-OS rather than writing a macOS LaunchAgent on
Linux.
"""

import os
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


def test_ci_workflow_does_not_install_sox(ci_workflow: str):
    # The audio backend is sounddevice/PortAudio, not sox; no CI job may install
    # a dependency the project does not have. The real-model tests synthesize
    # their clips with numpy for exactly this reason.
    assert "command -v sox" not in ci_workflow
    assert "brew install sox" not in ci_workflow
    assert "apt-get install" not in ci_workflow or "sox" not in ci_workflow


def test_real_seam_job_excludes_the_tts_module(ci_workflow: str):
    """The `say`-dependent module must stay out of CI, and explicitly.

    Its synthesis is not byte-stable between runs, so it flakes; it earns its
    keep locally. Pinning the exclusion keeps it from silently coming back in,
    and keeps the reason attached to it.
    """
    job = _ci_job(ci_workflow, "test-macos-real-seam")
    assert "--ignore=tests/test_transcription_quality.py" in job


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


# ---------------------------------------------------------------------------
# packaging/macos/reinstall.sh (make reinstall)
# ---------------------------------------------------------------------------

REINSTALL = ROOT / "packaging" / "macos" / "reinstall.sh"
MAKEFILE = ROOT / "Makefile"


@pytest.fixture(scope="module")
def reinstall() -> str:
    return REINSTALL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def reinstall_code(reinstall: str) -> str:
    """reinstall.sh with comment lines stripped.

    Ordering and absence assertions must look at what the script *does*, not at
    what its comments say about it -- several comments deliberately quote the
    very commands the script must not run.
    """
    return "\n".join(line for line in reinstall.splitlines() if not line.lstrip().startswith("#"))


@pytest.fixture(scope="module")
def makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def test_reinstall_script_exists_and_is_executable():
    assert REINSTALL.is_file()
    assert os.access(REINSTALL, os.X_OK), "make reinstall invokes it directly"


def test_reinstall_uses_strict_bash(reinstall: str):
    assert "set -euo pipefail" in reinstall


def test_reinstall_builds_before_stopping_the_app(reinstall_code: str):
    # Order is the whole fail-safe: a build failure must leave the running app
    # untouched. Quitting first trades a working app for a broken build.
    build = reinstall_code.index("build_app.sh")
    quit_ = reinstall_code.index("to quit")
    assert build < quit_, "the build must run before the running app is quit"


def test_reinstall_checks_for_a_running_process_before_the_apple_event(reinstall_code: str):
    # `tell application "Whispy" to quit` resolves through LaunchServices and
    # can LAUNCH the app to deliver the event -- so it must be gated on a real
    # process, or a fresh install would start the app it is about to replace.
    pgrep = reinstall_code.index("pgrep")
    quit_ = reinstall_code.index("to quit")
    assert pgrep < quit_


def test_reinstall_waits_on_pids_not_only_on_the_port(reinstall: str):
    # The daemon's SIGTERM handler releases :9090 before the process exits, so
    # a free port does not prove the old instance is gone.
    assert "kill -0" in reinstall


def test_reinstall_replaces_applications_only_after_the_app_is_stopped(reinstall_code: str):
    quit_ = reinstall_code.index("to quit")
    replace = reinstall_code.index('rm -rf "$APP_DST"')
    assert quit_ < replace, "never replace a bundle that is still executing"


def test_reinstall_installs_to_applications(reinstall: str):
    assert 'APP_DST="/Applications/Whispy.app"' in reinstall
    assert 'mv "$APP_STAGE" "$APP_DST"' in reinstall


def test_reinstall_stages_the_copy(reinstall: str):
    # An interrupted copy must not leave a half-written bundle at $APP_DST.
    assert "APP_STAGE=" in reinstall
    assert 'ditto "$APP_SRC" "$APP_STAGE"' in reinstall


def test_reinstall_launches_the_installed_copy_not_dist(reinstall_code: str):
    # Both bundles declare com.whispy, so `open dist/Whispy.app` may start the
    # /Applications copy instead -- the exact trap this target exists to avoid.
    assert '/usr/bin/open "$APP_DST"' in reinstall_code
    assert "open dist/Whispy.app" not in reinstall_code


def test_reinstall_never_skips_the_build_on_a_build_hash(reinstall_code: str):
    # bootstrap.sh skips when .whispy-build-hash == git HEAD. That is correct
    # for bootstrap and a footgun here: uncommitted edits do not move HEAD, so
    # the skip would ship the previous bundle while reporting success.
    assert "rev-parse HEAD" not in reinstall_code
    assert "INSTALLED_HASH" not in reinstall_code


def test_reinstall_waits_for_the_daemon_to_answer(reinstall: str):
    assert "check_daemon" in reinstall
    assert "9090" in reinstall


def test_reinstall_warns_when_the_bundle_is_adhoc_signed(reinstall: str):
    # Ad-hoc signing silently breaks TCC grant persistence.
    assert "Signature=adhoc" in reinstall
    assert "create_signing_cert.sh" in reinstall


def test_makefile_exposes_reinstall(makefile: str):
    assert "\nreinstall:" in makefile
    assert "./packaging/macos/reinstall.sh" in makefile
    phony = next(line for line in makefile.splitlines() if line.startswith(".PHONY:"))
    assert "reinstall" in phony


def test_reinstall_never_touches_user_settings(reinstall_code: str):
    # Settings, the bearer token and the model cache all live outside the
    # bundle (~/.config/whispy, ~/.cache). Reinstalling must replace the app
    # and nothing else -- a reinstall that resets the user's trigger key or
    # rotates their API token would be worse than the manual steps it replaces.
    assert ".config/whispy" not in reinstall_code
    assert "config.json" not in reinstall_code
    assert "config.token" not in reinstall_code
    assert "$HOME" not in reinstall_code
    assert ".cache" not in reinstall_code
    # The only paths it may remove are the bundle and its staging directory.
    # rstrip("'") because one removal lives inside a trap: trap 'rm -rf "$APP_STAGE"' EXIT
    removed = {m.rstrip("'") for m in re.findall(r"rm -rf (\S+)", reinstall_code)}
    assert removed <= {'"$APP_DST"', '"$APP_STAGE"'}, removed

"""Tests for the install scripts: scripts/bootstrap.sh (the one-liner),
packaging/linux/reinstall.sh (Linux: build, replace V1, systemd --user unit)
and packaging/macos-v2/reinstall.sh, plus the Makefile entry points.

The Linux installer also runs for real here, in a throwaway checkout, with
stubs for cargo and systemctl (Linux only): it must replace a V1 install and
leave whispy2 running as its unit. The real end to end, on a fresh Debian with
systemd, is v2/whispy2/linux-e2e/install.sh.
"""

import os
import platform
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "scripts" / "bootstrap.sh"
LINUX_REINSTALL = ROOT / "packaging" / "linux" / "reinstall.sh"
MAC_REINSTALL = ROOT / "packaging" / "macos-v2" / "reinstall.sh"
MAKEFILE = ROOT / "Makefile"


def _code(text: str) -> str:
    """The script without its comment lines: ordering assertions look at what it does."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


@pytest.fixture(scope="module")
def bootstrap() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def linux() -> str:
    return LINUX_REINSTALL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", [BOOTSTRAP, LINUX_REINSTALL, MAC_REINSTALL])
def test_scripts_are_strict_executable_bash(script: Path):
    assert os.access(script, os.X_OK)
    assert "set -euo pipefail" in script.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(script)], check=True)


# ---------------------------------------------------------------------------
# scripts/bootstrap.sh
# ---------------------------------------------------------------------------


def test_bootstrap_has_no_blocking_prompt(bootstrap: str):
    # Run as `curl | bash`: stdin is the script itself.
    assert "read -r -p" not in bootstrap
    assert "read -p" not in bootstrap


def test_bootstrap_package_manager_never_reads_the_piped_script(bootstrap: str):
    assert '"$@" </dev/null' in bootstrap


def test_bootstrap_installs_linux_build_packages_with_each_package_manager(bootstrap: str):
    assert "apt-get install -y" in bootstrap
    assert "dnf install -y" in bootstrap
    assert "pacman -S --needed --noconfirm" in bootstrap
    assert "WHISPY_SKIP_SYSTEM_PACKAGES" in bootstrap
    # What building whispy2 needs, on each distribution.
    for package in (
        "build-essential",
        "libasound2-dev",
        "libxkbcommon-dev",
        "libclang-dev",
        "libssl-dev",
        "libnotify-bin",
    ):
        assert package in bootstrap, f"apt: {package}"
    for package in ("gcc-c++", "alsa-lib-devel", "libxkbcommon-devel", "clang-devel", "openssl-devel"):
        assert package in bootstrap, f"dnf: {package}"
    for package in ("base-devel", "alsa-lib", "libxkbcommon", "libnotify"):
        assert package in bootstrap, f"pacman: {package}"
    assert "cmake" in bootstrap and "clang" in bootstrap and "pkg-config" in bootstrap


def test_bootstrap_linux_builds_v2_and_never_v1(bootstrap: str):
    code = _code(bootstrap)
    linux = code[code.index("install_linux() {") :]
    linux = linux[: linux.index("\n}\n")]
    assert "ensure_rust" in linux and "ensure_cmake" in linux
    assert '"$WHISPY_HOME/packaging/linux/reinstall.sh"' in linux
    # No Python on the Linux route any more.
    assert "python3" not in linux and 'install.sh"' not in linux.replace("reinstall.sh", "")
    assert "python3-venv" not in bootstrap and "libportaudio2" not in bootstrap


def test_bootstrap_installs_v2_on_macos(bootstrap: str):
    assert "packaging/macos-v2/reinstall.sh" in bootstrap
    assert "sh.rustup.rs" in bootstrap
    # V1 must not linger: its login item would bring it back and keep the key.
    assert "retire_v1" in bootstrap and ".Trash" in bootstrap


def test_bootstrap_uninstall_removes_the_linux_unit(bootstrap: str):
    block = bootstrap[bootstrap.index('if [[ "${1:-}" == "--uninstall" ]]') :]
    block = block[: block.index("\nfi\n")]
    assert '"$WHISPY_HOME/packaging/linux/reinstall.sh" --uninstall' in block
    # A checkout from before V2 reached Linux still has V1's own uninstaller.
    assert '"$WHISPY_HOME/install.sh" --uninstall </dev/null' in block


# ---------------------------------------------------------------------------
# packaging/linux/reinstall.sh, as text
# ---------------------------------------------------------------------------


def test_linux_reinstall_builds_before_touching_the_install(linux: str):
    code = _code(linux)
    build = code.index("cargo build --release --locked -p whispy2")
    assert build < code.index("\nretire_v1\n")
    assert build < code.index('install -m 755 "$BUILT"')
    assert build < code.index('systemctl --user restart "$UNIT"')


def test_linux_reinstall_retires_the_v1_unit_and_venv(linux: str):
    retire = linux[linux.index("retire_v1() {") :]
    retire = retire[: retire.index("\n}\n")]
    assert 'systemctl --user disable --now "$V1_UNIT"' in retire
    assert 'rm -f "$v1_unit_path"' in retire
    assert 'rm -rf "$REPO_ROOT/.venv"' in retire
    assert 'V1_UNIT="whispy.service"' in linux
    # The settings V1 and V2 share stay.
    assert "config.json" not in retire.replace("config.json is kept", "").replace("config.json are kept", "")


def test_linux_unit_runs_whispy2_with_the_session(linux: str):
    unit = linux[linux.index("<< UNITEOF") : linux.index("\nUNITEOF")]
    assert "ExecStart=%h/.local/bin/whispy2" in unit
    assert "Restart=on-failure" in unit
    assert "PassEnvironment=DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_SESSION_TYPE" in unit
    assert "WantedBy=$START_TARGET" in unit
    assert 'START_TARGET="graphical-session.target"' in linux
    assert 'UNIT="whispy2.service"' in linux


def test_linux_reinstall_enables_restarts_and_waits_for_the_socket(linux: str):
    code = _code(linux)
    assert 'systemctl --user enable "$UNIT"' in code
    assert code.index('systemctl --user enable "$UNIT"') < code.index('systemctl --user restart "$UNIT"')
    assert code.index('systemctl --user restart "$UNIT"') < code.index('"$BIN" send status')


def test_linux_reinstall_links_omarchy_when_present(linux: str):
    assert "command -v omarchy-dictation" in linux
    assert 'packaging/omarchy/omarchy-dictation-whispy" "$BIN_DIR/omarchy-dictation-whispy"' in linux
    assert 'packaging/omarchy/whispy-panel" "$PLUGIN_DIR/whispy-panel"' in linux
    # Omarchy binds the keys only when the backend's own program is on PATH.
    assert 'ln -sfn "$BIN" "$BIN_DIR/whispy"' in linux


# ---------------------------------------------------------------------------
# packaging/linux/reinstall.sh, run for real on stubs
# ---------------------------------------------------------------------------

V1_UNIT = """[Unit]
Description=Whispy voice dictation daemon
[Service]
ExecStart=/home/me/.local/share/whispy/.venv/bin/python3 /home/me/.local/share/whispy/whispy_daemon.py
[Install]
WantedBy=default.target
"""

FAKE_WHISPY2 = """#!/bin/sh
[ "$1" = send ] && [ "$2" = status ] && { echo '{"state":"idle","models_loaded":false}'; exit 0; }
exit 2
"""


def _write_exe(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def sandbox(tmp_path: Path):
    """A checkout holding V1 leftovers, a HOME with V1's unit, and stub tools."""
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "packaging", repo / "packaging")
    (repo / "v2").mkdir()
    (repo / ".venv" / "bin").mkdir(parents=True)
    home = tmp_path / "home"
    units = home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    (units / "whispy.service").write_text(V1_UNIT, encoding="utf-8")
    (home / ".config" / "whispy").mkdir(parents=True)
    (home / ".config" / "whispy" / "config.json").write_text('{"trigger_mode": "toggle"}', encoding="utf-8")
    (home / ".config" / "whispy" / "config.token").write_text("secret", encoding="utf-8")
    _write_exe(home / ".local" / "bin" / "whispy", "#!/bin/sh\nexec python3 whispy_daemon.py\n")
    stubs = tmp_path / "stubs"
    log = tmp_path / "calls.log"
    target = tmp_path / "target"
    # cargo "builds" a whispy2 that answers `send status`.
    _write_exe(
        stubs / "cargo",
        f'#!/bin/sh\necho "cargo $*" >> {log}\nmkdir -p {target}/release\n'
        f"cat > {target}/release/whispy2 <<'EOF'\n{FAKE_WHISPY2}EOF\nchmod +x {target}/release/whispy2\n",
    )
    _write_exe(stubs / "systemctl", f'#!/bin/sh\necho "systemctl $*" >> {log}\nexit 0\n')
    # Never a real process of this machine: pkill only says whether one matched.
    _write_exe(stubs / "pkill", f'#!/bin/sh\necho "pkill $*" >> {log}\nexit 1\n')
    env = {
        "HOME": str(home),
        "PATH": f"{stubs}:/usr/bin:/bin",
        "CARGO_TARGET_DIR": str(target),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "DISPLAY": ":0",
    }
    return {"repo": repo, "home": home, "units": units, "log": log, "env": env}


linux_only = pytest.mark.skipif(platform.system() != "Linux", reason="packaging/linux/reinstall.sh is Linux only")


@linux_only
def test_linux_reinstall_replaces_a_v1_install(sandbox):
    result = subprocess.run(
        [str(sandbox["repo"] / "packaging" / "linux" / "reinstall.sh")],
        env=sandbox["env"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = sandbox["log"].read_text(encoding="utf-8")
    home, units = sandbox["home"], sandbox["units"]

    # Criterion 2: the V1 unit is stopped and removed, its venv and wrapper gone, settings kept.
    assert "systemctl --user disable --now whispy.service" in calls
    assert not (units / "whispy.service").exists()
    assert not (sandbox["repo"] / ".venv").exists()
    assert not (home / ".config" / "whispy" / "config.token").exists()
    assert (home / ".config" / "whispy" / "config.json").read_text(encoding="utf-8") == '{"trigger_mode": "toggle"}'

    # Criterion 1: whispy2 installed and run as its unit, which answers.
    assert "cargo build --release --locked -p whispy2" in calls
    installed = home / ".local" / "bin" / "whispy2"
    assert installed.is_file() and os.access(installed, os.X_OK)
    assert (home / ".local" / "bin" / "whispy").resolve() == installed.resolve()
    unit = (units / "whispy2.service").read_text(encoding="utf-8")
    assert "ExecStart=%h/.local/bin/whispy2" in unit
    assert "systemctl --user enable whispy2.service" in calls
    assert "systemctl --user restart whispy2.service" in calls
    assert "systemctl --user import-environment DISPLAY" in calls
    assert '"state":"idle"' in result.stdout


@linux_only
def test_linux_uninstall_removes_unit_and_binary_and_keeps_data(sandbox):
    script = str(sandbox["repo"] / "packaging" / "linux" / "reinstall.sh")
    subprocess.run([script], env=sandbox["env"], check=True, capture_output=True, timeout=60)
    result = subprocess.run([script, "--uninstall"], env=sandbox["env"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    home = sandbox["home"]
    assert "systemctl --user disable --now whispy2.service" in sandbox["log"].read_text(encoding="utf-8")
    assert not (sandbox["units"] / "whispy2.service").exists()
    assert not (home / ".local" / "bin" / "whispy2").exists()
    assert not (home / ".local" / "bin" / "whispy").exists()
    assert (home / ".config" / "whispy" / "config.json").exists()


@linux_only
def test_linux_reinstall_leaves_the_install_alone_when_the_build_fails(sandbox):
    stubs = Path(sandbox["env"]["PATH"].split(":")[0])
    _write_exe(stubs / "cargo", "#!/bin/sh\nexit 101\n")
    result = subprocess.run(
        [str(sandbox["repo"] / "packaging" / "linux" / "reinstall.sh")],
        env=sandbox["env"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "Build failed" in result.stderr
    assert (sandbox["units"] / "whispy.service").exists(), "V1 must stay until a V2 is built"
    assert (sandbox["repo"] / ".venv").exists()


# ---------------------------------------------------------------------------
# packaging/macos-v2 and the Makefile
# ---------------------------------------------------------------------------


def test_macos_bundle_uses_its_own_signing_script_and_committed_icon():
    build = (ROOT / "packaging" / "macos-v2" / "build_bundle.sh").read_text(encoding="utf-8")
    assert '"$SCRIPT_DIR/create_signing_cert.sh"' in build
    assert '"$SCRIPT_DIR/whispy.icns"' in build
    assert (ROOT / "packaging" / "macos-v2" / "whispy.icns").is_file()
    assert "packaging/macos/" not in build
    assert not (ROOT / "packaging" / "macos").exists()


def test_makefile_reinstall_routes_by_os(makefile: str):
    assert re.search(r"^reinstall:", makefile, re.M)
    assert "./packaging/macos-v2/reinstall.sh" in makefile
    assert "./packaging/linux/reinstall.sh" in makefile
    for gone in ("whispy_daemon.py", "packaging/macos/", "doctor", "validate"):
        assert gone not in makefile


def test_v1_sources_are_gone():
    for gone in ("src", "whispy_daemon.py", "install.sh", "packaging/macos"):
        assert not (ROOT / gone).exists(), f"{gone} is V1 and must be gone (it lives at the tag v1)"


# ---------------------------------------------------------------------------
# The website says what each OS gets
# ---------------------------------------------------------------------------


def test_website_install_section_says_what_each_os_gets():
    site = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    install = site[site.index('id="install"') :]
    assert "Whispy V2.app" in install
    assert "apt" in install and "dnf" in install and "pacman" in install
    assert "whispy2" in install and "~/.local/bin" in install
    # One command on each OS: no manual package pre-step.
    assert "sudo apt install" not in install

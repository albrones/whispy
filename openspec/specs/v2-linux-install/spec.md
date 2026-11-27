# v2-linux-install Specification

## Purpose
How Whispy V2 gets onto a Linux machine and stays there: the one-line
installer (`scripts/bootstrap.sh`) installs the build tools, builds `whispy2`
and runs it as the `systemd --user` unit `whispy2.service`
(`packaging/linux/reinstall.sh`), replacing a Python V1 install. Card 3/3 of
the Linux switch to V2 (albrones/whispy#54).

## Requirements

### Requirement: One command installs V2 on a fresh Linux
On Linux, `scripts/bootstrap.sh` SHALL install the missing build packages with apt, dnf or pacman through sudo (a C/C++ toolchain, cmake, clang, pkg-config, the ALSA and xkbcommon headers, curl, notify-send and the session's clipboard tool; `WHISPY_SKIP_SYSTEM_PACKAGES=1` opts out), install Rust with rustup when `cargo` is missing, build `whispy2`, install it as `~/.local/bin/whispy2`, write, enable and start the unit `whispy2.service`, and wait until the control socket answers `status`.

#### Scenario: Fresh Debian
- **WHEN** the one-liner runs on a Debian with no Rust, compiler or cmake
- **THEN** `whispy2.service` SHALL be enabled and active, and a Right Ctrl dictation under X11 SHALL type its text

_Tier: live — `v2/whispy2/linux-e2e/install.sh`._

#### Scenario: After a new login
- **WHEN** the user logs out and in again
- **THEN** the unit SHALL start with the session (wanted by `graphical-session.target` when the installing session had it active, else `default.target`) and a dictation SHALL type its text

_Tier: live — `v2/whispy2/linux-e2e/install.sh` (user manager stopped and started)._

### Requirement: A V1 install is replaced
When the installer finds Whispy V1 (its `whispy.service` unit, a running `whispy_daemon.py`, its `.venv`, its `whispy` wrapper or its API token), it SHALL stop and remove them, after V2 is built and before V2 starts; the shared `~/.config/whispy/config.json` and the Parakeet cache V1 downloaded SHALL be kept. A failed build SHALL leave the V1 install untouched.

#### Scenario: Rerun over V1
- **WHEN** the one-liner runs where the one-liner of the tag `v1` installed V1
- **THEN** `whispy.service` SHALL be stopped, disabled and its file removed, no `whispy_daemon.py` SHALL run, and `whispy2.service` SHALL be active

_Tier: live — `v2/whispy2/linux-e2e/install.sh`; unit-mocked — `tests/test_install_scripts.py` (the script on stubbed `cargo` and `systemctl`)._

### Requirement: Uninstall keeps the user's data
`bootstrap.sh --uninstall` (and `packaging/linux/reinstall.sh --uninstall`) SHALL disable and remove `whispy2.service`, `~/.local/bin/whispy2`, the `whispy` link and the Omarchy links, and keep `~/.config/whispy` and `~/.whispy`.

#### Scenario: Uninstall
- **WHEN** the uninstaller runs
- **THEN** the unit and the binary SHALL be gone and the settings SHALL remain

_Tier: unit-mocked — `tests/test_install_scripts.py`._

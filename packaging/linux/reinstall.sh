#!/usr/bin/env bash
# Build Whispy V2 (whispy2) for Linux, install it as ~/.local/bin/whispy2,
# replace a Whispy V1 install, run it as the `systemd --user` unit
# whispy2.service and wait until its control socket answers `status`.
# scripts/bootstrap.sh runs it after installing the build tools; run it again
# after every change (`make v2-reinstall`): a plain restart reruns the old build.
#
# Usage (from anywhere):  ./packaging/linux/reinstall.sh
#         ./packaging/linux/reinstall.sh --uninstall
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/whispy2"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="whispy2.service"
UNIT_PATH="$UNIT_DIR/$UNIT"
V1_UNIT="whispy.service"
PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"
SOCK="${WHISPY_V2_SOCKET:-$HOME/.whispy/v2/control.sock}"
LOG="$HOME/.whispy/v2/whispy2.log"

die() { echo -e "${RED}[FAIL] $*${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}[!] $*${NC}" >&2; }
info() { echo -e "${YELLOW}$*${NC}"; }
ok() { echo -e "${GREEN}[OK] $*${NC}"; }

have_user_systemd() { command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }

# Whispy V1 (Python): its systemd --user unit, its venv and its `whispy`
# wrapper. Its settings (~/.config/whispy/config.json) are V2's too and stay,
# as does the Parakeet cache it downloaded, which V2 reuses.
retire_v1() {
    local v1_unit_path="$UNIT_DIR/$V1_UNIT" found=""
    if [ -f "$v1_unit_path" ]; then
        found=1
        if have_user_systemd; then
            systemctl --user disable --now "$V1_UNIT" >/dev/null 2>&1 || true
        fi
        rm -f "$v1_unit_path"
        have_user_systemd && systemctl --user daemon-reload || true
        ok "Whispy V1 unit stopped and removed ($V1_UNIT)"
    fi
    # A V1 started by hand: it holds the trigger key and V2 would step aside.
    if pkill -f 'whispy_daemon\.py' 2>/dev/null; then
        found=1
        ok "Whispy V1 process stopped"
    fi
    if [ -d "$REPO_ROOT/.venv" ]; then
        found=1
        rm -rf "$REPO_ROOT/.venv"
        ok "Whispy V1 virtual environment removed"
    fi
    # V1's wrapper script; V2 puts a link to whispy2 in its place below.
    if [ -f "$BIN_DIR/whispy" ] && [ ! -L "$BIN_DIR/whispy" ]; then
        found=1
        rm -f "$BIN_DIR/whispy"
    fi
    rm -f "$HOME/.config/whispy/config.token"
    [ -n "$found" ] && echo "    Your settings in ~/.config/whispy/config.json are kept."
    return 0
}

uninstall() {
    retire_v1
    if have_user_systemd; then
        systemctl --user disable --now "$UNIT" >/dev/null 2>&1 || true
    fi
    rm -f "$UNIT_PATH"
    have_user_systemd && systemctl --user daemon-reload || true
    rm -f "$BIN" "$BIN_DIR/whispy" "$BIN_DIR/omarchy-dictation-whispy"
    rm -f "$PLUGIN_DIR/whispy-panel"
    ok "Whispy removed (unit, ~/.local/bin/whispy2, Omarchy links)"
    echo "    Kept: settings in ~/.config/whispy, models and logs in ~/.whispy."
    echo "    Delete those folders to get the space back."
}

if [ "${1:-}" = "--uninstall" ]; then
    uninstall
    exit 0
fi

[ "$(uname -s)" = "Linux" ] || die "Linux only (macOS: packaging/macos-v2/reinstall.sh)."

# --- 1. Build first: a failed build leaves the installed Whispy alone ------
info "=== 1/5 Building whispy2 (the first build takes several minutes) ==="
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
command -v cargo >/dev/null 2>&1 || die "cargo not found: install Rust (https://rustup.rs) or run scripts/bootstrap.sh."
# clang builds whisper.cpp everywhere (GCC 12 cannot build its ARM kernels).
command -v clang >/dev/null 2>&1 && export CC="${CC:-clang}" CXX="${CXX:-clang++}"
(cd "$REPO_ROOT/v2" && cargo build --release --locked -p whispy2) || die "Build failed — the installed Whispy is untouched."
TARGET_DIR="${CARGO_TARGET_DIR:-$REPO_ROOT/v2/target}"
BUILT="$TARGET_DIR/release/whispy2"
[ -x "$BUILT" ] || die "Build reported success but $BUILT is missing."
ok "Built $BUILT"

# --- 2. Retire Whispy V1 -----------------------------------------------------
info "=== 2/5 Replacing Whispy V1, if present ==="
retire_v1

# --- 3. Install the binary and the Omarchy pieces ----------------------------
info "=== 3/5 Installing ~/.local/bin/whispy2 ==="
mkdir -p "$BIN_DIR"
# A copy, renamed into place: the running whispy2 keeps its file until restart.
install -m 755 "$BUILT" "$BIN.incoming"
mv -f "$BIN.incoming" "$BIN"
# Omarchy binds its dictation keys only when the backend's own program, named
# like the backend (`whispy`), is on PATH.
ln -sfn "$BIN" "$BIN_DIR/whispy"
ok "whispy2 installed: $BIN"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "$BIN_DIR is not on your PATH: the unit does not need it, the whispy2 command does." ;; esac

if command -v omarchy-dictation >/dev/null 2>&1; then
    # Symlinks, so they follow this checkout on every update.
    ln -sfn "$REPO_ROOT/packaging/omarchy/omarchy-dictation-whispy" "$BIN_DIR/omarchy-dictation-whispy"
    ok "Omarchy dictation backend linked: $BIN_DIR/omarchy-dictation-whispy"
    if [ -d "$(dirname "$PLUGIN_DIR")" ]; then
        mkdir -p "$PLUGIN_DIR"
        ln -sfn "$REPO_ROOT/packaging/omarchy/whispy-panel" "$PLUGIN_DIR/whispy-panel"
        if command -v omarchy-bar >/dev/null 2>&1 && ! grep -q '"whispy.panel"' "$(dirname "$PLUGIN_DIR")/shell.json" 2>/dev/null; then
            omarchy-bar put whispy.panel --section right --index 1 >/dev/null 2>&1 || true
        fi
        ok "Omarchy bar widget linked: $PLUGIN_DIR/whispy-panel (pick the dictation key there)"
    fi
    # The key file Omarchy loads while Whispy is the backend, for the saved
    # preset; rewritten so an update restores it.
    KEY=$("$REPO_ROOT/packaging/omarchy/omarchy-dictation-whispy" shortcuts) \
        && ok "Dictation key ($KEY) written to ~/.config/whispy/shortcuts.lua"
    if [ "$(omarchy-default-dictation 2>/dev/null || true)" != "whispy" ]; then
        echo "    Select Whispy as the dictation backend once:"
        echo "      omarchy-dictation-use whispy && hyprctl reload"
    fi
fi

# --- 4. The systemd --user unit ----------------------------------------------
info "=== 4/5 Running it as the systemd --user unit $UNIT ==="
if ! have_user_systemd; then
    warn "No systemd user session here: Whispy is installed but not started."
    echo "    From your desktop session, run: whispy2"
    exit 0
fi
mkdir -p "$UNIT_DIR"
# A session that activates graphical-session.target (Hyprland under uwsm,
# GNOME, KDE) imports WAYLAND_DISPLAY/DISPLAY into the user manager when it
# does; binding the unit to that target starts Whispy once they are there,
# after every login. Other sessions never activate the target: default.target.
START_TARGET="default.target"
if systemctl --user is-active --quiet graphical-session.target 2>/dev/null; then
    START_TARGET="graphical-session.target"
fi
cat > "$UNIT_PATH" << UNITEOF
[Unit]
Description=Whispy voice dictation (V2)
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.local/bin/whispy2
Restart=on-failure
RestartSec=2
# The session's display variables, imported into the user manager.
PassEnvironment=DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_SESSION_TYPE
# notify-send, wl-copy and xclip are not always in /usr/bin.
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=$START_TARGET
UNITEOF
ok "Unit written: $UNIT_PATH (started with $START_TARGET)"
# This terminal's display, for a session that does not import it itself.
for var in DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_SESSION_TYPE; do
    [ -n "${!var:-}" ] && systemctl --user import-environment "$var" 2>/dev/null || true
done
systemctl --user daemon-reload
# Re-enabled, so a unit moved to another target drops its old link.
systemctl --user disable "$UNIT" >/dev/null 2>&1 || true
systemctl --user enable "$UNIT" >/dev/null 2>&1 || die "systemctl --user enable $UNIT failed."
systemctl --user reset-failed "$UNIT" >/dev/null 2>&1 || true
systemctl --user restart "$UNIT" || die "systemctl --user restart $UNIT failed: journalctl --user -u whispy2"

# --- 5. Wait for its control socket ----------------------------------------------
info "=== 5/5 Waiting for Whispy to answer ==="
answer=""
for _ in $(seq 1 60); do
    answer="$("$BIN" send status 2>/dev/null || true)"
    [ -n "$answer" ] && break
    sleep 0.5
done
[ -n "$answer" ] || die "Whispy did not answer on $SOCK within 30 s. See: journalctl --user -u whispy2, $LOG"
ok "Whispy answers: $answer"

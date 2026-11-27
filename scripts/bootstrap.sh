#!/usr/bin/env bash
set -euo pipefail

# Whispy one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash
#
# Clones (or updates) Whispy into a managed directory, then routes by OS:
#   macOS  -> Whispy V2 (Rust): installs the Rust toolchain and cmake when they
#             are missing, builds and signs "Whispy V2.app", installs it to
#             /Applications and launches it. The app downloads its speech
#             models on first launch. A V1 Whispy.app is quit and moved to the
#             Trash: V2 is the only macOS version.
#   Linux  -> Whispy V2 (Rust): installs the missing system packages (apt,
#             dnf or pacman, through sudo), the Rust toolchain when it is
#             missing, then packaging/linux/reinstall.sh: builds whispy2,
#             installs it to ~/.local/bin and runs it as the systemd --user
#             unit whispy2.service. A Whispy V1 install (Python venv and its
#             whispy.service unit) is stopped and removed.
#
# Rerunning it updates an existing install.
#
# Environment overrides:
#   WHISPY_HOME    install location (default: ~/.local/share/whispy)
#   WHISPY_REPO    git URL (default: https://github.com/albrones/whispy.git)
#   WHISPY_REF     branch/tag to check out (default: main)
#   WHISPY_SKIP_SYSTEM_PACKAGES=1   Linux: never call the package manager
#
# Uninstall:
#   curl -fsSL .../bootstrap.sh | bash -s -- --uninstall

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

WHISPY_HOME="${WHISPY_HOME:-$HOME/.local/share/whispy}"
WHISPY_REPO="${WHISPY_REPO:-https://github.com/albrones/whispy.git}"
WHISPY_REF="${WHISPY_REF:-main}"
OS="$(uname -s)"

V2_APP="/Applications/Whispy V2.app"
V2_BUNDLE_ID="com.whispy.v2"
V1_APP="/Applications/Whispy.app"

echo -e "${YELLOW}=== Whispy bootstrap ===${NC}"
echo ""

# --- Uninstall ---------------------------------------------------------------
# Settings (~/.config/whispy) and models (~/.whispy) are kept: a reinstall
# would otherwise download the models again.
if [[ "${1:-}" == "--uninstall" ]]; then
    if [ "$OS" = "Darwin" ] && [ -d "$V2_APP" ]; then
        echo -e "${YELLOW}Quitting and removing $V2_APP...${NC}"
        if pgrep -f "$V2_APP/Contents/MacOS/whispy2" >/dev/null 2>&1; then
            osascript -e "tell application id \"$V2_BUNDLE_ID\" to quit" >/dev/null 2>&1 \
                || pkill -f "$V2_APP/Contents/MacOS/whispy2" || true
        fi
        rm -rf "$V2_APP"
        echo "Its models stay in ~/.whispy/models (delete that folder to get the space back)."
    fi
    if [ "$OS" = "Linux" ] && [ -x "$WHISPY_HOME/packaging/linux/reinstall.sh" ]; then
        "$WHISPY_HOME/packaging/linux/reinstall.sh" --uninstall || true
    elif [ -x "$WHISPY_HOME/install.sh" ]; then
        # A checkout from before V2 reached Linux: V1's own uninstaller.
        "$WHISPY_HOME/install.sh" --uninstall </dev/null || true
    fi
    echo -e "${YELLOW}Removing $WHISPY_HOME...${NC}"
    rm -rf "$WHISPY_HOME"
    echo -e "${GREEN}Uninstallation complete.${NC}"
    exit 0
fi

# --- Linux: system packages ----------------------------------------------------
# Runs as root directly, else through sudo. sudo asks for the password on the
# terminal (/dev/tty), which works under `curl | bash`; the package manager's
# own stdin is /dev/null so it never eats the rest of this script.
as_root() {
    if [ "$(id -u)" = "0" ]; then
        "$@" </dev/null
    else
        sudo "$@" </dev/null
    fi
}

linux_session() {
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        echo wayland
    else
        echo x11
    fi
}

# Is package $2 installed, for package manager $1?
linux_has_package() {
    case "$1" in
        apt) dpkg-query -W -f='${Status}' "$2" 2>/dev/null | grep -q 'ok installed' ;;
        dnf) rpm -q --whatprovides "$2" >/dev/null 2>&1 ;;
        pacman) pacman -Q "$2" >/dev/null 2>&1 || pacman -Qg "$2" >/dev/null 2>&1 ;;
    esac
}

# Prints the packages this machine lacks, named for package manager $1: what
# building whispy2 needs (a C/C++ toolchain, cmake and clang for whisper.cpp,
# pkg-config with the ALSA and xkbcommon headers), curl (rustup, and the
# models at first launch), notify-send for alerts, and the session's clipboard
# tool (the 5-minute watchdog leaves the text there).
linux_missing_packages() {
    local manager="$1" wanted=() missing=() package
    case "$manager" in
        apt) wanted=(git curl ca-certificates build-essential cmake clang libclang-dev pkg-config libasound2-dev libxkbcommon-dev libnotify-bin) ;;
        dnf) wanted=(git curl gcc gcc-c++ make cmake clang clang-devel pkgconf-pkg-config alsa-lib-devel libxkbcommon-devel libnotify) ;;
        pacman) wanted=(git curl base-devel cmake clang pkgconf alsa-lib libxkbcommon libnotify) ;;
    esac
    if [ "$(linux_session)" = "wayland" ]; then
        wanted+=(wl-clipboard)
    else
        wanted+=(xclip)
    fi
    for package in "${wanted[@]}"; do
        linux_has_package "$manager" "$package" || missing+=("$package")
    done
    echo "${missing[*]:-}"
}

install_linux_packages() {
    local manager="" packages
    if command -v apt-get >/dev/null 2>&1; then manager=apt
    elif command -v dnf >/dev/null 2>&1; then manager=dnf
    elif command -v pacman >/dev/null 2>&1; then manager=pacman
    fi
    if [ -z "$manager" ]; then
        echo -e "${YELLOW}[!] No apt, dnf or pacman here. Install git, curl, a C/C++ toolchain, cmake, clang,${NC}"
        echo -e "${YELLOW}    pkg-config, the ALSA and xkbcommon headers and notify-send yourself.${NC}"
        return 0
    fi
    packages="$(linux_missing_packages "$manager")"
    if [ -z "$packages" ]; then
        echo -e "${GREEN}[OK] System packages present${NC}"
        return 0
    fi
    if [ "${WHISPY_SKIP_SYSTEM_PACKAGES:-}" = "1" ]; then
        echo -e "${YELLOW}[!] Missing system packages (not installed, WHISPY_SKIP_SYSTEM_PACKAGES=1): $packages${NC}"
        return 0
    fi
    echo -e "${YELLOW}Installing system packages with $manager (sudo may ask for your password): $packages${NC}"
    # shellcheck disable=SC2086
    if case "$manager" in
        apt) as_root apt-get update -qq && as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y $packages ;;
        dnf) as_root dnf install -y $packages ;;
        pacman) as_root pacman -S --needed --noconfirm $packages ;;
    esac; then
        echo -e "${GREEN}[OK] System packages installed${NC}"
    else
        echo -e "${RED}[!] Could not install: $packages${NC}"
        echo "    Install them yourself, then rerun this command."
    fi
}

if [ "$OS" = "Linux" ]; then
    install_linux_packages
    echo ""
fi

# --- Prerequisites ---------------------------------------------------------------
if [ "$OS" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
    # git, the compiler, codesign and install_name_tool all come with them.
    echo -e "${YELLOW}Whispy is built on this Mac and needs the Xcode Command Line Tools.${NC}"
    xcode-select --install >/dev/null 2>&1 || true
    echo "A dialog to install them has opened. Once it is done, rerun:"
    echo "  curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash"
    exit 1
fi

if ! command -v git &>/dev/null; then
    echo -e "${RED}Error: git is not installed. Install it and rerun.${NC}"
    exit 1
fi

# --- Source ------------------------------------------------------------------------
if [ -d "$WHISPY_HOME/.git" ]; then
    echo -e "${YELLOW}Updating existing install at $WHISPY_HOME...${NC}"
    # FETCH_HEAD, not origin/<ref>: a clone made with --branch main --depth 1
    # tracks main only, so another branch or a tag never gets a remote ref.
    git -C "$WHISPY_HOME" fetch --depth 1 origin "$WHISPY_REF"
    git -C "$WHISPY_HOME" checkout --quiet --force --detach FETCH_HEAD
else
    echo -e "${YELLOW}Cloning Whispy into $WHISPY_HOME...${NC}"
    mkdir -p "$(dirname "$WHISPY_HOME")"
    git clone --depth 1 --branch "$WHISPY_REF" "$WHISPY_REPO" "$WHISPY_HOME"
fi
echo -e "${GREEN}[OK] Source ready at $WHISPY_HOME${NC}"
echo ""

# --- Whispy V2: the toolchain ----------------------------------------------------------
ensure_rust() {
    [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
    if command -v cargo >/dev/null 2>&1; then
        echo -e "${GREEN}[OK] Rust $(cargo --version | awk '{print $2}')${NC}"
        return 0
    fi
    echo -e "${YELLOW}Installing the Rust toolchain (rustup, into ~/.cargo)...${NC}"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
    . "$HOME/.cargo/env"
    echo -e "${GREEN}[OK] Rust $(cargo --version | awk '{print $2}')${NC}"
}

# cmake builds whisper.cpp. Linux: the system package (installed above).
# macOS: Homebrew's when there is a Homebrew, else the cmake wheel in a
# private venv (python3 comes with the Command Line Tools).
ensure_cmake() {
    local tools="$WHISPY_HOME/.tools"
    [ -x "$tools/bin/cmake" ] && export PATH="$tools/bin:$PATH"
    if command -v cmake >/dev/null 2>&1; then
        echo -e "${GREEN}[OK] cmake $(cmake --version | awk 'NR==1{print $3}')${NC}"
        return 0
    fi
    if [ "$OS" = "Linux" ]; then
        echo -e "${RED}Error: cmake is missing. Install it with your package manager and rerun.${NC}"
        exit 1
    fi
    echo -e "${YELLOW}Installing cmake...${NC}"
    if command -v brew >/dev/null 2>&1; then
        brew install cmake
    else
        python3 -m venv "$tools"
        "$tools/bin/pip" install --quiet cmake
        export PATH="$tools/bin:$PATH"
    fi
    echo -e "${GREEN}[OK] cmake $(cmake --version | awk 'NR==1{print $3}')${NC}"
}

# V2 is the only macOS version: a V1 left running would keep the trigger key,
# and its login item would start it again. Removing the bundle drops that
# login item; the Trash keeps it recoverable.
retire_v1() {
    for id in com.whisper-dictation com.whispy; do
        local plist="$HOME/Library/LaunchAgents/$id.plist"
        if [ -f "$plist" ]; then
            echo -e "${YELLOW}Removing legacy $id LaunchAgent...${NC}"
            launchctl bootout "gui/$(id -u)/$id" 2>/dev/null || true
            launchctl unload "$plist" 2>/dev/null || true
            rm -f "$plist"
        fi
    done
    [ -d "$V1_APP" ] || return 0
    echo -e "${YELLOW}Retiring Whispy V1 ($V1_APP)...${NC}"
    if pgrep -f "$V1_APP/Contents/MacOS/" >/dev/null 2>&1; then
        osascript -e 'tell application "Whispy" to quit' >/dev/null 2>&1 \
            || pkill -f "$V1_APP/Contents/MacOS/" || true
        sleep 2
    fi
    local trashed
    trashed="$HOME/.Trash/Whispy V1 $(date +%Y%m%d-%H%M%S).app"
    if mv "$V1_APP" "$trashed" 2>/dev/null; then
        echo -e "${GREEN}[OK] Whispy V1 moved to the Trash${NC}"
    else
        echo -e "${YELLOW}[!] Could not move $V1_APP to the Trash: quit it and delete it yourself.${NC}"
    fi
}

install_macos() {
    ensure_rust
    ensure_cmake
    retire_v1

    local current installed=""
    current="$(git -C "$WHISPY_HOME" rev-parse HEAD)"
    [ -f "$V2_APP/Contents/Resources/.whispy-build-hash" ] \
        && installed="$(cat "$V2_APP/Contents/Resources/.whispy-build-hash")"
    if [ "$current" = "$installed" ]; then
        echo -e "${GREEN}[OK] $V2_APP is up to date ($current)${NC}"
        open "$V2_APP"
    else
        echo -e "${YELLOW}Building and installing Whispy V2 (the first build takes a few minutes)...${NC}"
        # Builds, quits the running V2, replaces it, launches it, waits for it.
        "$WHISPY_HOME/packaging/macos-v2/reinstall.sh"
    fi
    echo ""
    echo -e "${GREEN}Whispy is installed.${NC} Look for its waveform in the menu bar."
    echo "First launch downloads the speech models (about 1.2 GB); the menu says"
    echo "Ready when you can dictate. Then, once:"
    echo "  - grant Whispy V2 Microphone, Input Monitoring and Accessibility"
    echo "    (System Settings → Privacy & Security);"
    echo "  - set Keyboard → \"Press 🌐 key to\" → Do Nothing, to dictate with Fn;"
    echo "  - check \"Start at login\" in its menu."
}

install_linux() {
    ensure_rust
    ensure_cmake
    # Builds whispy2, replaces a V1 install, installs ~/.local/bin/whispy2 and
    # the whispy2.service unit, starts it and waits for it.
    "$WHISPY_HOME/packaging/linux/reinstall.sh"
    echo ""
    echo -e "${GREEN}Whispy is installed.${NC} It starts with your session (systemd --user unit whispy2)."
    echo "First launch downloads the speech models (about 1.2 GB) into ~/.whispy/models."
    if [ "$(linux_session)" = "wayland" ]; then
        echo "Wayland: bind a key of your compositor to dictate:"
        echo "  press: whispy2 send start   release: whispy2 send stop   (or: whispy2 send toggle)"
        echo "  Omarchy: omarchy-dictation-use whispy && hyprctl reload, then hold the key"
        echo "  picked in Whispy's bar panel (Right Option by default)."
    else
        echo "X11: hold Right Ctrl while you speak, release to insert the text."
    fi
    echo "Logs: journalctl --user -u whispy2 -f   (and ~/.whispy/v2/whispy2.log)"
}

case "$OS" in
Linux)
    install_linux
    ;;
Darwin)
    install_macos
    ;;
*)
    echo -e "${RED}Unsupported OS: $OS. Whispy supports macOS and Linux.${NC}"
    exit 1
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

# Whispy one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash
#
# Clones (or updates) Whispy into a managed directory and runs install.sh from
# there. The source must persist at a stable path because install.sh performs an
# editable install and the LaunchAgent points at whispy_daemon.py / icons/.
#
# Environment overrides:
#   WHISPY_HOME    install location (default: ~/.local/share/whispy)
#   WHISPY_REPO    git URL (default: https://github.com/albrones/whispy.git)
#   WHISPY_REF     branch/tag to check out (default: main)
#   WHISPER_MODEL  whisper model passed through to install.sh (default: small)
#
# Uninstall:
#   curl -fsSL .../bootstrap.sh | bash -s -- --uninstall

# Colors (matched to install.sh)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

WHISPY_HOME="${WHISPY_HOME:-$HOME/.local/share/whispy}"
WHISPY_REPO="${WHISPY_REPO:-https://github.com/albrones/whispy.git}"
WHISPY_REF="${WHISPY_REF:-main}"

echo -e "${YELLOW}=== Whispy bootstrap ===${NC}"
echo ""

# Uninstall path: delegate to install.sh, then remove the managed source tree.
if [[ "${1:-}" == "--uninstall" ]]; then
    if [ -x "$WHISPY_HOME/install.sh" ]; then
        echo -e "${YELLOW}Running Whispy uninstall...${NC}"
        "$WHISPY_HOME/install.sh" --uninstall || true
    fi
    echo -e "${YELLOW}Removing $WHISPY_HOME...${NC}"
    rm -rf "$WHISPY_HOME"
    echo -e "${GREEN}Uninstallation complete.${NC}"
    exit 0
fi

# Check for git
if ! command -v git &>/dev/null; then
    echo -e "${RED}Error: git is not installed. Install it (e.g. xcode-select --install) and rerun.${NC}"
    exit 1
fi

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install it and rerun this script.${NC}"
    exit 1
fi

# Check for sox; offer to install via brew if available.
if ! command -v sox &>/dev/null; then
    if command -v brew &>/dev/null; then
        echo -e "${YELLOW}sox is required and not installed.${NC}"
        # Skip the prompt when stdin is not a TTY (e.g. piped from curl).
        if [ -t 0 ]; then
            read -r -p "Install it now with 'brew install sox'? [y/N] " reply
        else
            reply="n"
        fi
        if [[ "$reply" =~ ^[Yy]$ ]]; then
            brew install sox
        else
            echo -e "${YELLOW}Install sox and rerun: brew install sox${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Error: sox is not installed and Homebrew was not found.${NC}"
        echo -e "${YELLOW}Install Homebrew (https://brew.sh) then: brew install sox${NC}"
        exit 1
    fi
fi

# Clone or update the source tree.
if [ -d "$WHISPY_HOME/.git" ]; then
    echo -e "${YELLOW}Updating existing install at $WHISPY_HOME...${NC}"
    git -C "$WHISPY_HOME" fetch --depth 1 origin "$WHISPY_REF"
    git -C "$WHISPY_HOME" checkout "$WHISPY_REF"
    git -C "$WHISPY_HOME" reset --hard "origin/$WHISPY_REF"
else
    echo -e "${YELLOW}Cloning Whispy into $WHISPY_HOME...${NC}"
    mkdir -p "$(dirname "$WHISPY_HOME")"
    git clone --depth 1 --branch "$WHISPY_REF" "$WHISPY_REPO" "$WHISPY_HOME"
fi
echo -e "${GREEN}[OK] Source ready at $WHISPY_HOME${NC}"
echo ""

# Hand off to the existing installer (creates venv, icons, LaunchAgent).
# WHISPER_MODEL is honored by install.sh if exported.
exec "$WHISPY_HOME/install.sh"

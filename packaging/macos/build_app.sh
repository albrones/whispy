#!/usr/bin/env bash
# Build, icon, and ad-hoc code-sign Whispy.app.
#
# Produces dist/Whispy.app — a self-contained menu-bar app with its own Python
# interpreter, so macOS mic / Accessibility / Input-Monitoring grants attach to
# a stable "Whispy" identity (survives interpreter upgrades).
#
# Usage (from anywhere):  ./packaging/macos/build_app.sh
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

# Resolve repo root from this script's location, then run everything from there
# (setup_app.py uses repo-relative paths).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

VENV_PY="$REPO_ROOT/.venv/bin/python"
[ -x "$VENV_PY" ] || { echo -e "${RED}No .venv — run ./install.sh first.${NC}"; exit 1; }

echo -e "${YELLOW}=== Whispy.app build ===${NC}"

# 1. Ensure py2app is available in the venv.
if ! "$VENV_PY" -c "import py2app" 2>/dev/null; then
    echo -e "${YELLOW}Installing py2app...${NC}"
    "$REPO_ROOT/.venv/bin/pip" install -q py2app
fi

# 2. (Re)generate the app icon.
echo -e "${YELLOW}Generating app icon (.icns)...${NC}"
"$VENV_PY" "$SCRIPT_DIR/make_icns.py"

# 3. Clean previous build output, then build with py2app.
#    Stash pyproject.toml during the build: from the repo root setuptools would
#    otherwise merge its [project].dependencies into install_requires, which
#    py2app rejects ("install_requires is no longer supported"). The `whispy`
#    package is already importable from the venv, so py2app needs no metadata.
echo -e "${YELLOW}Building bundle (py2app)...${NC}"
rm -rf "$REPO_ROOT/build" "$REPO_ROOT/dist/Whispy.app"
PYPROJECT="$REPO_ROOT/pyproject.toml"
STASH="$REPO_ROOT/pyproject.toml.buildstash"
restore_pyproject() { [ -f "$STASH" ] && mv -f "$STASH" "$PYPROJECT"; }
trap restore_pyproject EXIT
mv -f "$PYPROJECT" "$STASH"
"$VENV_PY" "$SCRIPT_DIR/setup_app.py" py2app
restore_pyproject
trap - EXIT

APP="$REPO_ROOT/dist/Whispy.app"
[ -d "$APP" ] || { echo -e "${RED}Build failed: $APP not found.${NC}"; exit 1; }

# 3b. Prune dangling symlinks (py2app's optimize step leaves a broken
#     lib/pythonX.Y/site.pyo link) — codesign --verify --strict fails on them.
"$VENV_PY" - "$APP" <<'PY'
import os, sys
root = sys.argv[1]
for dirpath, dirnames, filenames in os.walk(root):
    for n in list(dirnames) + filenames:
        p = os.path.join(dirpath, n)
        if os.path.islink(p) and not os.path.exists(p):
            os.unlink(p)
PY

# 4. Code-sign with the hardened runtime + entitlements.
#    Prefer the self-signed "Whispy Local Signing" identity: a stable signing
#    identity is what lets macOS TCC PERSIST the microphone / Accessibility /
#    Input-Monitoring grants across relaunches. An ad-hoc ("-") signature has no
#    stable identity, so TCC re-prompts (or auto-denies) every launch. Fall back
#    to ad-hoc only if the identity is absent (run create_signing_cert.sh).
CERT_NAME="Whispy Local Signing"
"$SCRIPT_DIR/create_signing_cert.sh" || true
if security find-identity -p codesigning 2>/dev/null | grep -q "$CERT_NAME"; then
    SIGN_ID="$CERT_NAME"
    echo -e "${YELLOW}Code-signing with '$CERT_NAME' (stable identity, TCC persists)...${NC}"
else
    SIGN_ID="-"
    echo -e "${RED}No '$CERT_NAME' identity — falling back to ad-hoc (TCC will NOT persist).${NC}"
fi
codesign --force --deep --options runtime \
    --entitlements "$SCRIPT_DIR/whispy.entitlements" \
    --sign "$SIGN_ID" "$APP"

# 5. Verify.
echo -e "${YELLOW}Verifying signature...${NC}"
codesign --verify --strict --verbose=2 "$APP"
codesign -dv --verbose=4 "$APP" 2>&1 | grep -E "Identifier|Signature|flags" || true

echo -e "${GREEN}[OK] Built and signed: $APP${NC}"
echo
echo "Install:   cp -R \"$APP\" /Applications/"
echo "First run: launch it, hold the push-to-talk key, speak — accept the"
echo "           'Whispy' microphone prompt. Then check System Settings ->"
echo "           Privacy & Security -> Microphone shows \"Whispy\"."

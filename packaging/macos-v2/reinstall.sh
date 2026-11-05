#!/usr/bin/env bash
# Rebuild Whispy V2.app, replace the installed copy, relaunch it, and wait
# until its control socket answers `status`. Never touches /Applications/Whispy.app (V1).
#
# Usage (from anywhere):  ./packaging/macos-v2/reinstall.sh
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_SRC="$REPO_ROOT/dist/Whispy V2.app"
APP_DST="/Applications/Whispy V2.app"
APP_STAGE="/Applications/.Whispy V2.app.incoming"
V1_BIN="/Applications/Whispy.app/Contents/MacOS/Whispy"
BUNDLE_ID="com.whispy.v2"
SOCK="${WHISPY_V2_SOCKET:-$HOME/.whispy/v2/control.sock}"
LOG="$HOME/.whispy/v2/whispy2.log"
PROC_PATTERN='/Whispy V2.app/Contents/MacOS/whispy2'

die() { echo -e "${RED}[FAIL] $*${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}[warn] $*${NC}" >&2; }
info() { echo -e "${YELLOW}$*${NC}"; }

sock_answers() { printf 'status\n' | nc -U "$SOCK" 2>/dev/null | head -n 1 || true; }  # set -e + pipefail: no socket yet must not end the script

# --- 0. Preflight (no side effects) ----------------------------------------
[ "$(uname -s)" = "Darwin" ] || die "macOS only."
[ -w /Applications ] || die "/Applications is not writable by $(id -un)."
if [ -e "$APP_DST" ] && [ ! -w "$APP_DST" ]; then
    die "$APP_DST is not writable (root-owned?). Remove it with sudo, then rerun."
fi

V1_SUM_BEFORE=""
[ -f "$V1_BIN" ] && V1_SUM_BEFORE="$(shasum -a 256 "$V1_BIN" | awk '{print $1}')"

# --- 1. Build first: a failed build must leave the running app alone -------
info "=== 1/5 Building ==="
"$SCRIPT_DIR/build_bundle.sh" || die "Build failed — $APP_DST left untouched."
[ -d "$APP_SRC" ] || die "Build reported success but $APP_SRC is missing."
if codesign -dvv "$APP_SRC" 2>&1 | grep -q 'Signature=adhoc'; then
    warn "Bundle is ad-hoc signed — TCC grants will NOT persist."
    warn "Fix: ./packaging/macos/create_signing_cert.sh, then rerun."
fi

# --- 2. Quit the running V2 -------------------------------------------------
info "=== 2/5 Stopping Whispy V2 ==="
pids="$(pgrep -f "$PROC_PATTERN" || true)"
if [ -z "$pids" ]; then
    echo "  not running — nothing to stop"
else
    echo "  running as pid(s): $pids"
    # Gated on a real process: the Apple Event could otherwise launch V2.
    if osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1; then
        grace=10
    else
        warn "Apple Event refused (System Settings → Privacy & Security → Automation)."
        kill -TERM $pids 2>/dev/null || true
        grace=3
    fi
    # Wait for the process and the socket to be gone.
    deadline=$(( $(date +%s) + grace ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        still=""
        for pid in $pids; do kill -0 "$pid" 2>/dev/null && still="$still $pid"; done
        if [ -z "$still" ] && [ -z "$(sock_answers)" ]; then break; fi
        sleep 0.2
    done
    still=""
    for pid in $pids; do kill -0 "$pid" 2>/dev/null && still="$still $pid"; done
    if [ -n "$still" ]; then
        warn "pid(s)$still did not exit in ${grace}s — force-quitting."
        kill -9 $still 2>/dev/null || true
        sleep 1
        for pid in $still; do
            kill -0 "$pid" 2>/dev/null && die "pid $pid will not die — nothing was replaced."
        done
    fi
    echo "  stopped"
fi

# --- 3. Install -------------------------------------------------------------
info "=== 3/5 Installing to $APP_DST ==="
rm -rf "$APP_STAGE"
trap 'rm -rf "$APP_STAGE"' EXIT
ditto "$APP_SRC" "$APP_STAGE"
rm -rf "$APP_DST"
mv "$APP_STAGE" "$APP_DST"
trap - EXIT

# V1 must be byte-for-byte untouched.
if [ -n "$V1_SUM_BEFORE" ]; then
    V1_SUM_AFTER="$(shasum -a 256 "$V1_BIN" | awk '{print $1}')"
    [ "$V1_SUM_BEFORE" = "$V1_SUM_AFTER" ] \
        || die "V1 executable CHANGED ($V1_SUM_BEFORE -> $V1_SUM_AFTER). This must never happen."
    echo "  V1 executable unchanged (sha256 ${V1_SUM_AFTER:0:12}…)"
fi

# --- 4. Relaunch ------------------------------------------------------------
info "=== 4/5 Relaunching ==="
/usr/bin/open "$APP_DST"

# --- 5. Wait for the control socket ----------------------------------------
info "=== 5/5 Waiting for $SOCK ==="
deadline=$(( $(date +%s) + 30 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    line="$(sock_answers)"
    if [ -n "$line" ]; then
        echo "  $line"
        echo -e "${GREEN}[OK] Whispy V2 reinstalled and running.${NC}"
        exit 0
    fi
    sleep 0.5
done
echo -e "${RED}[FAIL] Whispy V2 did not answer on $SOCK within 30s.${NC}" >&2
echo "       The install itself succeeded — no need to rebuild. Last log lines:" >&2
tail -n 30 "$LOG" >&2 2>/dev/null || echo "       (no log at $LOG)" >&2
exit 1

#!/usr/bin/env bash
# Rebuild Whispy.app, replace the installed copy, relaunch it, and wait until
# the daemon answers.
#
# The dev loop this replaces is: quit from the menu bar, `make app`,
# `cp -R dist/Whispy.app /Applications/`, relaunch. Skipping any of those steps
# silently leaves the OLD build running, which is the usual reason a code fix
# appears not to take (README "How do I update Whispy?").
#
# Usage (from anywhere):  ./packaging/macos/reinstall.sh
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_SRC="$REPO_ROOT/dist/Whispy.app"
APP_DST="/Applications/Whispy.app"
# Dot-prefixed so LaunchServices does not register a second com.whispy while
# the copy is in flight.
APP_STAGE="/Applications/.Whispy.app.incoming"
PORT=9090
# Matches both the installed bundle and a dist/ copy, so a stray instance of
# either is found.
PROC_PATTERN='/Whispy.app/Contents/MacOS/'

die() { echo -e "${RED}[FAIL] $*${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}[warn] $*${NC}" >&2; }
info() { echo -e "${YELLOW}$*${NC}"; }

# --- 0. Preflight -----------------------------------------------------------
# Everything that can fail without side effects runs here, BEFORE the running
# app is touched. Discovering /Applications is unwritable after quitting the
# user's app would leave them with no Whispy and no new build.

[ "$(uname -s)" = "Darwin" ] || die "macOS only. On Linux, rerun ./install.sh (it reloads the systemd unit)."
[ -w /Applications ] || die "/Applications is not writable by $(id -un)."
if [ -e "$APP_DST" ] && [ ! -w "$APP_DST" ]; then
    die "$APP_DST is not writable (root-owned?). Remove it with sudo, then rerun."
fi

# --- 1. Build FIRST ---------------------------------------------------------
# Deliberately before the quit: a build failure must leave the running app
# alone. The reverse order trades a working app for a broken build.

info "=== 1/5 Building ==="
"$SCRIPT_DIR/build_app.sh" || die "Build failed — $APP_DST left untouched."
[ -d "$APP_SRC" ] || die "Build reported success but $APP_SRC is missing."

# An ad-hoc signature is not a build failure, but macOS TCC will not persist
# the mic / Accessibility / Input-Monitoring grants across launches, so every
# run re-prompts. Worth saying out loud rather than letting the user rediscover
# it as "Whispy keeps asking for permissions".
if codesign -dvv "$APP_SRC" 2>&1 | grep -q 'Signature=adhoc'; then
    warn "Bundle is ad-hoc signed — TCC grants will NOT persist."
    warn "Fix: ./packaging/macos/create_signing_cert.sh, then rerun."
fi

# --- 2. Quit the running instance, and prove it is gone ---------------------

info "=== 2/5 Stopping Whispy ==="
# Gate on a real process. `tell application "Whispy" to quit` resolves the name
# through LaunchServices and can LAUNCH the app in order to deliver the event —
# so sending it blind would start the very app we are about to replace.
pids="$(pgrep -f "$PROC_PATTERN" || true)"

if [ -z "$pids" ]; then
    echo "  not running — nothing to stop"
else
    echo "  running as pid(s): $pids"
    # Quitting is an Apple Event, so the SENDING terminal needs Automation
    # permission for Whispy. On denial osascript exits non-zero and the app
    # never sees the event; `make update` discards that and carries on, which
    # is how it ends up rebuilding around a still-running instance.
    if osascript -e 'tell application "Whispy" to quit' >/dev/null 2>&1; then
        grace=10
    else
        warn "Apple Event refused (System Settings → Privacy & Security → Automation)."
        warn "Falling back to a signal. Grant Automation to your terminal for a clean quit."
        kill -TERM $pids 2>/dev/null || true
        grace=3
    fi

    # Wait on the PIDs, not on the port. The daemon's SIGTERM handler releases
    # :9090 (http_server.shutdown()) before the process actually exits, so a
    # free port does not prove the old instance is gone — it can still own the
    # event tap and the menu-bar icon.
    deadline=$(( $(date +%s) + grace ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        still=""
        for pid in $pids; do kill -0 "$pid" 2>/dev/null && still="$still $pid"; done
        [ -z "$still" ] && break
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

# Belt and braces: the new instance needs this bind to succeed, and :9090 is
# the single-instance lock.
deadline=$(( $(date +%s) + 5 ))
while lsof -ti "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
    [ "$(date +%s)" -lt "$deadline" ] || die "127.0.0.1:$PORT still bound — nothing was replaced."
    sleep 0.2
done

# --- 3. Install -------------------------------------------------------------
# Stage then rename, so an interrupted copy (disk full, Ctrl-C) can never leave
# a half-written bundle sitting at $APP_DST. The rename is same-volume.
# `ditto` is Apple's bundle copier and preserves xattrs/ACLs exactly.

info "=== 3/5 Installing to $APP_DST ==="
rm -rf "$APP_STAGE"
trap 'rm -rf "$APP_STAGE"' EXIT
ditto "$APP_SRC" "$APP_STAGE"
rm -rf "$APP_DST"
mv "$APP_STAGE" "$APP_DST"
trap - EXIT
echo "  installed build $(cat "$APP_DST/Contents/Resources/.whispy-build-hash" 2>/dev/null || echo '?')"

# --- 4. Relaunch ------------------------------------------------------------
# By explicit path. `open dist/Whispy.app` is ambiguous: both bundles declare
# com.whispy, so LaunchServices may start the installed copy instead.

info "=== 4/5 Relaunching ==="
/usr/bin/open "$APP_DST"

# --- 5. Wait for the daemon to answer ---------------------------------------
# Reuses whispy.doctor.check_daemon, which already reads the per-install bearer
# token and sends a request the API's host/origin guards accept. One python
# process for the whole loop, not one per attempt.

info "=== 5/5 Waiting for the daemon ==="
if "$REPO_ROOT/.venv/bin/python" - <<'PY'
import sys, time

sys.path.insert(0, "src")
from whispy.doctor import OK, check_daemon

deadline = time.monotonic() + 30.0
while time.monotonic() < deadline:
    res = check_daemon()
    if res.status == OK:
        print(f"  {res.detail}")
        sys.exit(0)
    # Anything starting with "running" means it ANSWERED (e.g. a 401 token
    # mismatch). That is a pre-existing condition, not a failed reinstall.
    if res.detail.startswith("running"):
        print(f"  {res.detail}")
        sys.exit(0)
    time.sleep(0.5)
sys.exit(1)
PY
then
    echo -e "${GREEN}[OK] Whispy reinstalled and running.${NC}"
else
    echo -e "${RED}[FAIL] Whispy did not answer on 127.0.0.1:$PORT within 30s.${NC}" >&2
    echo "       The install itself succeeded — no need to rebuild." >&2
    echo "       Logs:     tail -n 40 ~/.whispy-error.log ~/.whispy.log" >&2
    echo "       Diagnose: make doctor" >&2
    exit 1
fi

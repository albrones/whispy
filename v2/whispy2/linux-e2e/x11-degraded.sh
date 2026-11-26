#!/bin/bash
# Criterion 3 (no tray host) and criterion 4 (the X11 key cannot be listened to).
. /e2e/common.sh
eval $(dbus-launch --sh-syntax); export DBUS_SESSION_BUS_ADDRESS
start_audio
notifications() { grep -c . /tmp/notify.log; }
run_case() { # run_case <title> <DISPLAY>
  rm -rf $HOME/.whispy/v2; : > /tmp/notify.log
  python3 /e2e/notifyd.py > /tmp/notify.log 2>&1 &
  local MON=$!; sleep 0.5
  DISPLAY=$2 XDG_SESSION_TYPE=x11 /target/release/whispy2 > /tmp/whispy.out 2>&1 &
  local PID=$!
  wait_for 60 ready
  sleep 3
  echo "== $1"
  echo "   process alive after start: $(kill -0 $PID 2>/dev/null && echo yes || echo no)"
  echo "   socket status: $(ctl status)"
  echo "   notifications posted: $(notifications)"
  sed 's/^/   | /' /tmp/notify.log
  echo "   log:"; grep -E "tray icon|cannot listen|X11 trigger|panicked" $HOME/.whispy/v2/whispy2.log | cut -c1-260 | sed 's/^/   | /'
  echo "   socket start then stop still answer: $(ctl start) / $(sleep 1; ctl stop)"
  sleep 2; echo "   alive at the end: $(kill -0 $PID 2>/dev/null && echo yes || echo no)"
  kill $PID $MON 2>/dev/null; wait $PID 2>/dev/null || true
}
Xvfb :99 >/dev/null 2>&1 & wait_for 10 env DISPLAY=:99 xdpyinfo
run_case "X11 session, no tray host in the panel (criterion 3)" :99
run_case "X11 session, X server unreachable (criterion 4)" :98

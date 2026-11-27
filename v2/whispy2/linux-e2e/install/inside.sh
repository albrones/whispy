#!/bin/bash
# Runs as root inside the systemd container of ../install.sh. See there.
set -euo pipefail
U=e2e
UID_N=$(id -u $U)
RT=/run/user/$UID_N
H=/home/$U
RAW=https://raw.githubusercontent.com/albrones/whispy

as_user() {
  sudo -u $U env HOME=$H USER=$U XDG_RUNTIME_DIR=$RT DBUS_SESSION_BUS_ADDRESS=unix:path=$RT/bus \
    PATH=$H/.local/bin:$H/.cargo/bin:/usr/local/bin:/usr/bin:/bin LC_ALL=C.UTF-8 "$@"
}
uctl() { as_user systemctl --user "$@"; }
wait_for() { # wait_for <seconds> <command...>
  local limit=$1; shift; local i=0
  until "$@" >/dev/null 2>&1; do i=$((i+1)); [ $i -ge $((limit*5)) ] && return 1; sleep 0.2; done
}
say() { echo "== $*"; }

# The desktop session a login brings: an X server, the display imported into
# the user manager, then the session target, which starts graphical-session.target
# (as sway-session.target or a GNOME/KDE session does).
start_session() {
  wait_for 60 test -S $RT/bus
  as_user mkdir -p $H/.config/systemd/user
  as_user tee $H/.config/systemd/user/e2e-session.target >/dev/null <<'UNIT'
[Unit]
Description=The e2e desktop session
BindsTo=graphical-session.target
Wants=graphical-session-pre.target
After=graphical-session-pre.target
UNIT
  uctl daemon-reload
  as_user systemd-run --user --quiet --unit=e2e-xvfb Xvfb :99 -screen 0 1280x800x24
  wait_for 20 as_user env DISPLAY=:99 xdpyinfo
  uctl set-environment DISPLAY=:99 XDG_SESSION_TYPE=x11
  uctl start e2e-session.target
  wait_for 20 as_user pactl info
  as_user pactl load-module module-null-sink sink_name=voice >/dev/null
  as_user pactl set-default-source voice.monitor
}

# Holds Right Ctrl over a terminal while the clip plays, then reads what was typed.
dictate() {
  rm -f /tmp/typed.txt
  as_user systemd-run --user --quiet --collect --setenv=DISPLAY=:99 \
    xterm -geometry 100x5+0+0 -e bash -c 'read -r line; printf "%s" "$line" > /tmp/typed.txt'
  sleep 1.5
  as_user env DISPLAY=:99 xdotool mousemove 100 40
  as_user env DISPLAY=:99 xdotool keydown Control_R
  sleep 0.6
  as_user paplay -d voice /e2e/clip.wav
  sleep 0.8
  as_user env DISPLAY=:99 xdotool keyup Control_R
  wait_for 60 idle || true
  sleep 1
  as_user env DISPLAY=:99 xdotool key Return
  wait_for 10 test -s /tmp/typed.txt || true
  say "typed into xterm: [$(cat /tmp/typed.txt 2>/dev/null)]"
}

ready() { as_user whispy2 send status 2>/dev/null | grep -q '"models_loaded":true'; }
idle() { as_user whispy2 send status 2>/dev/null | grep -q '"state":"idle"'; }
unit_active() { uctl is-active --quiet whispy2.service; }

say "fresh machine: $(. /etc/os-release; echo "$PRETTY_NAME"); cargo=$(command -v cargo || echo none) cc=$(command -v cc || echo none) cmake=$(command -v cmake || echo none)"
wait_for 60 bash -c 'systemctl is-system-running 2>/dev/null | grep -qE "running|degraded"'
systemctl start user@$UID_N.service
start_session
say "session: graphical-session.target $(uctl is-active graphical-session.target)"

# The models, where V1 (Hugging Face cache) and V2 (~/.whispy/models) look.
as_user mkdir -p $H/.cache/huggingface/hub $H/.whispy/models
cp -a /models/hf $H/.cache/huggingface/hub/models--istupakov--parakeet-tdt-0.6b-v3-onnx
cp /models/ggml-small.bin $H/.whispy/models/ggml-small.bin
chown -R $U:$U $H/.cache $H/.whispy

say "### 1. Whispy V1, from the one-line installer of the tag v1"
as_user bash -c "curl -fsSL $RAW/v1/scripts/bootstrap.sh | WHISPY_REF=v1 DISPLAY=:99 XDG_SESSION_TYPE=x11 bash" > /tmp/v1-install.log 2>&1 \
  || { tail -30 /tmp/v1-install.log; exit 1; }
wait_for 60 bash -c "pgrep -u $U -f whispy_daemon.py" || true
say "V1 unit: enabled=$(uctl is-enabled whispy.service 2>&1) active=$(uctl is-active whispy.service 2>&1); V1 process: $(pgrep -u $U -fc whispy_daemon.py || true); venv: $(test -d $H/.local/share/whispy/.venv && echo yes || echo no)"

say "### 2. The one-line installer of $REF, over V1"
start=$(date +%s)
as_user bash -c "curl -fsSL $RAW/$REF/scripts/bootstrap.sh | WHISPY_REF=$REF DISPLAY=:99 XDG_SESSION_TYPE=x11 bash" > /tmp/v2-install.log 2>&1 \
  || { tail -40 /tmp/v2-install.log; exit 1; }
say "installer finished in $(( $(date +%s) - start )) s; its last lines:"
tail -12 /tmp/v2-install.log | sed 's/\x1b\[[0-9;]*m//g'
say "toolchain now: cargo=$(as_user bash -c 'command -v cargo') cmake=$(command -v cmake) clang=$(command -v clang)"
say "V1 unit: enabled=$(uctl is-enabled whispy.service 2>&1 || true) active=$(uctl is-active whispy.service 2>&1 || true) file=$(test -e $H/.config/systemd/user/whispy.service && echo present || echo absent)"
say "V1 process: $(pgrep -u $U -fc whispy_daemon.py || true); venv: $(test -d $H/.local/share/whispy/.venv && echo present || echo absent); V1 sources: $(test -e $H/.local/share/whispy/whispy_daemon.py && echo present || echo absent)"
say "V2 unit: enabled=$(uctl is-enabled whispy2.service) active=$(uctl is-active whispy2.service); WantedBy: $(grep WantedBy $H/.config/systemd/user/whispy2.service)"
say "settings kept: $(cat $H/.config/whispy/config.json 2>/dev/null | tr -d '\n' | cut -c1-120)"
wait_for 120 ready || { as_user whispy2 send status; tail -20 $H/.whispy/v2/whispy2.log; exit 1; }
say "status: $(as_user whispy2 send status)"
say "### 3. Dictation with Right Ctrl"
dictate
first=$(cat /tmp/typed.txt 2>/dev/null || true)

say "### 4. Log out, log in again"
systemctl stop user@$UID_N.service
say "logged out: whispy2 process $(pgrep -u $U -fc '/.local/bin/whispy2' || true)"
systemctl start user@$UID_N.service
start_session
wait_for 60 unit_active
say "after login: whispy2.service $(uctl is-active whispy2.service), started by $(uctl show -p TriggeredBy -p WantedBy whispy2.service | tr '\n' ' ')"
wait_for 120 ready || { as_user whispy2 send status; exit 1; }
dictate
second=$(cat /tmp/typed.txt 2>/dev/null || true)
say "log: $(grep -c . $H/.whispy/v2/whispy2.log) lines; last dictations:"
grep -i "outcome" $H/.whispy/v2/whispy2.log | tail -2 | cut -c1-200
[ -n "$first" ] && [ -n "$second" ] && say "PASS" || { say "FAIL"; exit 1; }

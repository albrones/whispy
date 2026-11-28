#!/bin/bash
# Card 2/3 of the Linux switch to V2: Omarchy's dictation keys and bar panel on
# Whispy V2's control socket, with no V1 and no network port (sway headless
# stands in for Hyprland: the same virtual-keyboard protocol).
#   1. the dictation binding starts and stops a V2 dictation through the socket;
#   2. the panel's real Service.qml, under Quickshell, reads the state, the
#      level and the last dictation from the socket; nothing listens on a port;
#   3. a key picked in the panel is saved and bound, and that binding dictates;
#   4. (card 3/3) the panel's power switch starts and stops whispy2.service and
#      its Start at login enables and disables it (systemctl as a stand-in).
. /e2e/common.sh
set -u
rm -rf $HOME/.whispy/v2 $HOME/.config/whispy
eval $(dbus-launch --sh-syntax); export DBUS_SESSION_BUS_ADDRESS
start_audio

# What Omarchy and the installer would have put in place, and no V1 at all.
mkdir -p $HOME/.local/bin /tmp/fakes /tmp/panel
ln -sf /src/packaging/omarchy/omarchy-dictation-whispy $HOME/.local/bin/omarchy-dictation-whispy
ln -sf /target/release/whispy2 $HOME/.local/bin/whispy2
cp /e2e/omarchy/omarchy-dictation /e2e/omarchy/hyprctl /e2e/omarchy/omarchy-shell /e2e/omarchy/systemctl /tmp/fakes/
printf '#!/bin/sh\necho "notify-send $*" >> /tmp/notify.log\n' > /tmp/fakes/notify-send; chmod +x /tmp/fakes/*
export PATH=$HOME/.local/bin:/tmp/fakes:$PATH
echo "== no V1: daemon=$(pgrep -fc whispy_daemon.py) token=$(ls $HOME/.config/whispy/config.token 2>/dev/null | wc -l) curl=$(grep -c curl /src/packaging/omarchy/omarchy-dictation-whispy)"

unset DISPLAY; export XDG_SESSION_TYPE=wayland
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 sway -c /e2e/sway.conf > /tmp/sway.log 2>&1 &
wait_for 15 bash -c 'ls $XDG_RUNTIME_DIR/wayland-* | grep -v lock' || { tail /tmp/sway.log; exit 1; }
export WAYLAND_DISPLAY=$(basename $(ls $XDG_RUNTIME_DIR/wayland-* | grep -v lock | head -1))
wtype -s 3600000 >/dev/null 2>&1 &
sleep 1

# The panel's service, as shipped, next to the harness that logs what it draws.
cp -r /src/packaging/omarchy/whispy-panel/Service.qml /src/packaging/omarchy/whispy-panel/Model.js /src/packaging/omarchy/whispy-panel/i18n /e2e/omarchy/shell.qml /tmp/panel/
panel() { QT_QPA_PLATFORM=offscreen qs -p /tmp/panel/shell.qml "$@"; }
# A shell function: wait_for runs it in this shell (a `bash -c` would not see `panel`).
panel_is() { panel ipc call whispy state | grep -q "$1"; }
panel > /tmp/panel.log 2>&1 &
QS=$!
wait_for 15 panel ipc call whispy state || { cat /tmp/panel.log; exit 1; }
echo "== panel before Whispy starts: $(panel ipc call whispy state)"

echo "== a key press with Whispy down: exit $(omarchy-dictation start >/dev/null 2>&1; echo $?), $(grep -c 'Whispy is not answering' /tmp/notify.log) notification"

rm -f /tmp/typed.txt
foot bash -c 'read -r line; printf "%s" "$line" > /tmp/typed.txt' > /tmp/foot.log 2>&1 &
sleep 2
whispy2 > /tmp/whispy.out 2>&1 &
PID=$!
wait_for 120 ready || { echo "not ready"; tail -20 $HOME/.whispy/v2/whispy2.log; exit 1; }
panel ipc call whispy refresh >/dev/null
wait_for 5 panel_is '^ready'
echo "== panel once Whispy runs: $(panel ipc call whispy state)"

echo "### criterion 3: pick Right Ctrl in the panel"
panel ipc call whispy pick right_ctrl_hold >/dev/null
wait_for 10 panel_is right_ctrl_hold
echo "== panel: $(panel ipc call whispy state)"
echo "== config.json: $(jq -c . $HOME/.config/whispy/config.json)"
echo "== shortcuts.lua binds: $(grep -o 'bind_hold("[^"]*"' $HOME/.config/whispy/shortcuts.lua | tr '\n' ' ')"
echo "== hyprctl: $(cat /tmp/hyprctl.log)"
# What Hyprland runs on Right Ctrl down and up, read from the file it loads.
binding=$(grep 'bind_hold("Control_R"' $HOME/.config/whispy/shortcuts.lua)
press=$(echo "$binding" | awk -F'"' '{print $6}')
release=$(echo "$binding" | awk -F'"' '{print $10}')
echo "== Right Ctrl down runs [$press], up runs [$release]"

echo "### criteria 1 and 2: hold Right Ctrl, say « Ajouter trois tests. », release"
bash -c "$press"; echo "== press: exit $?"
sleep 0.4
paplay -d voice /e2e/clip.wav
sleep 0.8
bash -c "$release"; echo "== release: exit $?"
wait_for 60 idle
wait_for 10 bash -c "grep -q 'panel: last=\[.\+\]' /tmp/panel.log"
sleep 1
wtype -k Return
wait_for 10 test -s /tmp/typed.txt
echo "== typed into foot: [$(cat /tmp/typed.txt)]"
echo "== the panel saw (phases, levels read during the dictation, last dictation):"
grep -E 'panel: (phase|last)' /tmp/panel.log | sed 's/^.*panel: /   /'
echo "   levels: $(grep -c 'panel: level=' /tmp/panel.log) readings above 0, max $(grep -o 'level=[0-9.]*' /tmp/panel.log | cut -d= -f2 | sort -n | tail -1)"
echo "== journal: $(tail -1 $HOME/.whispy/v2/dictations.jsonl)"
echo "== text on disk under ~/.whispy: $(grep -rl 'Ajouter' $HOME/.whispy 2>/dev/null | wc -l) file(s)"
echo "== TCP listeners in the container: [$(ss -Htln | tr -s ' ' | tr '\n' ';')]"
echo "== Unix listeners of whispy2: $(ss -Hxlp | grep -c 'whispy2') ($(ss -Hxlp | grep whispy2 | awk '{print $5}'))"

echo "### Whispy quits: the panel shows it stopped"
kill $PID; sleep 1
panel ipc call whispy refresh >/dev/null
wait_for 5 panel_is '^stopped'
echo "== panel: $(panel ipc call whispy state)"

# The fake user manager behind fakes/systemctl: runs whispy2 as the unit would.
mkfifo /tmp/unit.fifo
( while true; do
    read -r action < /tmp/unit.fifo
    case "$action" in
      start) whispy2 > /tmp/whispy-unit.out 2>&1 < /dev/null & echo $! > /tmp/unit.pid ;;
      stop) kill "$(cat /tmp/unit.pid 2>/dev/null)" 2>/dev/null; rm -f /tmp/unit.pid ;;
    esac
  done ) &
MANAGER=$!
echo "### card 3/3: the power switch and Start at login drive whispy2.service"
panel ipc call whispy power true >/dev/null
wait_for 120 panel_is '^ready' || { tail -25 /tmp/panel.log; exit 1; }
echo "== switch on: panel $(panel ipc call whispy state); whispy2 runs as pid $(cat /tmp/unit.pid)"
panel ipc call whispy login true >/dev/null
wait_for 10 panel_is 'login=true' || exit 1
echo "== Start at login on: panel $(panel ipc call whispy state); unit $(cat /tmp/unit.enabled)"
panel ipc call whispy login false >/dev/null
wait_for 10 panel_is 'login=false' || exit 1
echo "== Start at login off: unit $(cat /tmp/unit.enabled)"
panel ipc call whispy power false >/dev/null
wait_for 20 panel_is '^stopped' || { echo "panel: $(panel ipc call whispy state)"; ps -eo pid,args | grep [w]hispy2; cat /tmp/systemctl.log; tail -25 /tmp/panel.log; exit 1; }
echo "== switch off: panel $(panel ipc call whispy state); whispy2 alive? $(pgrep -fc '^whispy2$' || true)"
echo "== systemctl calls: $(tr '\n' ';' < /tmp/systemctl.log)"
echo "== the panel is still up: $(panel ipc call whispy state)"
kill $QS $MANAGER

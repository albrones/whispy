#!/bin/bash
# Criterion 2 under Wayland (sway headless, the virtual-keyboard protocol Hyprland also offers):
# the control socket starts and stops the dictation, enigo types the text.
. /e2e/common.sh
rm -rf $HOME/.whispy/v2
eval $(dbus-launch --sh-syntax); export DBUS_SESSION_BUS_ADDRESS
start_audio
unset DISPLAY; export XDG_SESSION_TYPE=wayland
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 sway -c /e2e/sway.conf > /tmp/sway.log 2>&1 &
wait_for 15 bash -c 'ls $XDG_RUNTIME_DIR/wayland-* | grep -v lock' || { tail /tmp/sway.log; exit 1; }
export WAYLAND_DISPLAY=$(basename $(ls $XDG_RUNTIME_DIR/wayland-* | grep -v lock | head -1))
# Headless sway has no physical keyboard: the seat would only gain one when a
# virtual keyboard appears, too late for the focused window. A virtual keyboard
# kept open for the whole run stands in for the user's keyboard.
wtype -s 3600000 >/dev/null 2>&1 &
sleep 1
echo "== compositor: sway $(sway --version | cut -d' ' -f3) on $WAYLAND_DISPLAY"
rm -f /tmp/typed.txt
foot bash -c 'read -r line; printf "%s" "$line" > /tmp/typed.txt' > /tmp/foot.log 2>&1 &
sleep 2
/target/release/whispy2 > /tmp/whispy.out 2>&1 &
PID=$!
wait_for 120 ready || { echo "not ready"; tail -20 $HOME/.whispy/v2/whispy2.log; exit 1; }
echo "== ready: $(ctl status)"
echo "== socket start: $(ctl start)"
sleep 0.4
echo "== status: $(ctl status)"
paplay -d voice /e2e/clip.wav
sleep 0.8
echo "== socket stop: $(ctl stop)"
sleep 1
wait_for 60 idle
sleep 1
wtype -k Return
wait_for 10 test -s /tmp/typed.txt
echo "== typed into foot: [$(cat /tmp/typed.txt)]"
echo "== journal: $(tail -1 $HOME/.whispy/v2/dictations.jsonl 2>/dev/null)"
echo "== tray under Wayland: $(grep -c 'tray icon' $HOME/.whispy/v2/whispy2.log) line(s) (none expected)"
echo "== log:"; grep -E "started|Wayland|dictation:|could not be typed|panicked" $HOME/.whispy/v2/whispy2.log | cut -c1-200
kill $PID

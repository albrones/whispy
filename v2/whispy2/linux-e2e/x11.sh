#!/bin/bash
# Criteria 1 and 3 under X11 (Xvfb): Right Ctrl held, « Ajouter trois tests » spoken, released.
. /e2e/common.sh
rm -rf $HOME/.whispy/v2
eval $(dbus-launch --sh-syntax); export DBUS_SESSION_BUS_ADDRESS
start_audio
Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 & export DISPLAY=:99 XDG_SESSION_TYPE=x11
wait_for 10 xdpyinfo
python3 /e2e/sni_watcher.py > /tmp/watcher.log 2>&1 &
sleep 1
rm -f /tmp/typed.txt
xterm -geometry 100x5+0+0 -e bash -c 'read -r line; printf "%s" "$line" > /tmp/typed.txt' &
sleep 1; xdotool mousemove 100 40
/target/release/whispy2 > /tmp/whispy.out 2>&1 &
PID=$!
wait_for 120 ready || { echo "not ready"; tail -20 $HOME/.whispy/v2/*.log; exit 1; }
echo "== ready: $(ctl status)"
ITEM=$(cat /tmp/sni_item)
echo "== tray registered as $ITEM"
pixel() { # pixel <x> <y> of the 22x22 icon, as « a r g b »
  local x=$1 y=$2
  gdbus call --session -d "$ITEM" -o /StatusNotifierItem -m org.freedesktop.DBus.Properties.Get org.kde.StatusNotifierItem IconPixmap | tr -d '[]<>(),' | awk -v x=$x -v y=$y '{
  n=0; for(i=1;i<=NF;i++){ if($i ~ /^0x/ || $i ~ /^[0-9]+$/){ n++; v[n]=$i } } off=3+(y*22+x)*4; print v[off], v[off+1], v[off+2], v[off+3] }'; }
echo "== icon at rest (a r g b): centre $(pixel 11 11), ring $(pixel 11 2)"
echo "== tray menu: $(gdbus call --session -d "$ITEM" -o /MenuBar -m com.canonical.dbusmenu.GetLayout -- 0 -1 '[]' | grep -o "'label': <'[^']*'>" | tr '\n' ' ')"
xdotool keydown Control_R
sleep 0.6
echo "== icon while listening (a r g b): centre $(pixel 11 11), ring $(pixel 11 2)"
echo "== status while held: $(ctl status)"
paplay -d voice /e2e/clip.wav
sleep 0.8
xdotool keyup Control_R
sleep 1
wait_for 60 idle
sleep 1
xdotool key Return
wait_for 10 test -s /tmp/typed.txt
echo "== typed into xterm: [$(cat /tmp/typed.txt)]"
echo "== journal: $(tail -1 $HOME/.whispy/v2/dictations.jsonl 2>/dev/null | cut -c1-300)"
# Quit from the tray menu: find the item labelled Quit and click it.
QUIT_ID=$(gdbus call --session -d "$ITEM" -o /MenuBar -m com.canonical.dbusmenu.GetLayout -- 0 -1 '[]' | grep -o "([0-9]*, {'label': <'Quit'>" | grep -o '[0-9]*' | head -1)
gdbus call --session -d "$ITEM" -o /MenuBar -m com.canonical.dbusmenu.Event -- "$QUIT_ID" clicked '<"">' 0 >/dev/null
wait_for 10 bash -c "! kill -0 $PID"
echo "== after Quit: process alive? $(kill -0 $PID 2>/dev/null && echo yes || echo no); socket left? $(test -e $SOCK && echo yes || echo no)"
echo "== log:"; grep -v "^$" $HOME/.whispy/v2/whispy2.log | cut -c1-200 | tail -25

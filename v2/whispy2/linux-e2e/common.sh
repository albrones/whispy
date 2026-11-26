export XDG_RUNTIME_DIR=/tmp/xdg-$(id -u)
mkdir -p -m700 $XDG_RUNTIME_DIR
export WHISPY_PARAKEET_DIR=/models/parakeet WHISPY_WHISPER_MODEL=/models/ggml-small.bin
SOCK=$HOME/.whispy/v2/control.sock
ctl() { echo "$1" | socat -t5 - UNIX-CONNECT:$SOCK 2>/dev/null; }
wait_for() { # wait_for <seconds> <command...>
  local limit=$1; shift; local i=0
  until "$@" >/dev/null 2>&1; do i=$((i+1)); [ $i -ge $((limit*5)) ] && return 1; sleep 0.2; done
}
ready() { ctl status | grep -q '"state":"idle"' && ctl status | grep -q '"models_loaded":true'; }
idle() { ctl status | grep -q '"state":"idle"'; }
start_audio() {
  pulseaudio -D --exit-idle-time=-1 >/dev/null 2>&1
  wait_for 10 pactl info
  pactl load-module module-null-sink sink_name=voice >/dev/null
  pactl set-default-source voice.monitor
}

# Design — V2 menu bar app

## Shape

```
main.rs (composition root, main thread: AppKit loop + Fn tap)
  ├─ mac::fn_key ──FnDown/FnUp/OtherKeyDown──▶ controller thread
  ├─ housekeeping thread ──Tick / V1Running / replayed FnUp──▶ controller thread
  │                                     owns Machine + Capture (mac::microphone)
  │                                     │ jobs: Transcribe(samples), Insert(text)
  │                                     ▼
  │                               worker thread: Pipeline (whispy-core) + Inserter
  │                                     │ Transcribed / TranscriptionFailed / Inserted
  │                                     └──────────▶ controller thread
  └─ mac::menu_bar ◀── Status (main queue) ── controller thread
```

`machine` is pure (events carry their `Instant`; it returns at most one
action). `controller` owns the ports `Capture` and `Inserter`; the macOS
adapters implement them, the tests use a WAV and a recorder.

## Decisions

### One state machine, events in, one action out
V1's freezes came from state spread over the tap, the engine and the audio
thread: a missed release left RECORDING with nobody able to leave it. Here
every transition is in `Machine::handle`, and every busy state has an exit
that the worker always sends (transcribed, failed, inserted). Fn edges are
tracked in the machine (`is_key_held`), so a repeated flagsChanged press is
ignored and a release without a press too.

### Fn from the flag, a missed release replayed
Fn's state is the secondary-Fn bit of each flagsChanged event on keycode 63,
not a diff with the previous flags (V1's `fix-modifier-trigger-flag-desync`).
macOS disables a tap whose callback is slow or under heavy input; the
housekeeping beat checks `CGEventTapIsEnabled` each second, re-enables it, and
when Fn was believed down but is up in the HID state, replays the release —
V1's re-arm resync. It does not replay presses: a live-state poll racing a
real press could cut a hold short.

### Tap = toggle, threshold 0.3 s
A release under 0.3 s after the press latches the recording; the next press
stops it and its release is ignored. Fn+another key while held cancels: Fn is
then a modifier (Fn+Delete), and a fast Fn+Delete would otherwise latch a
dictation nobody asked for.

### Dictate, then insert
No streaming: the whole dictation goes to `Pipeline::transcribe`, which splits
it in ≤ 20 s pieces itself. Simpler, and the measured release-to-text p95 is
0.37 s for 6.5 s of speech.

### Microphone per dictation, resampled in the app
The default input is opened at each press (a device plugged since is used,
the recording indicator is on only while dictating) at its own rate, then
averaged to mono and resampled to 16 kHz with a windowed sinc (Hann, 16 zero
crossings, cut-off at 92 % of 8 kHz). Tests check a 1 kHz tone keeps its level
from 48 and 44.1 kHz and a 12 kHz tone does not fold back.

### Insertion is V1's
Clipboard via `pbcopy` (UTF-8 locale forced), ⌘V through `osascript` →
System Events, previous clipboard restored 150 ms later. A refused keystroke
(error 1002) leaves the text on the clipboard and says so in the menu. After
the 5 min watchdog the text goes to the clipboard only.

### Cohabitation with V1: V2 yields
V1 is « running » when 127.0.0.1:9090 accepts a connection (V1's
single-instance lock) or a process runs `…/Whispy.app/Contents/MacOS/Whispy`.
Checked synchronously before the tap is installed, then every 2 s. While V1
runs the machine sits in `Yielded`, where Fn does nothing; a V1 appearing
mid-dictation lets that dictation finish, then V2 yields. The tap stays
installed (its events are dropped): reinstalling it on each change would ask
for Input Monitoring again on failure for no gain.

### Quit frees the models first
whisper.cpp's Metal device aborts the process (`GGML_ASSERT([rsets->data
count] == 0)`) when `exit` tears it down with a model loaded — seen in the
latency test. Quit runs `Controller::stop` (both threads joined, pipeline
dropped) before `terminate:`.

## Risks

- **Fn on non-Apple keyboards** may not send keycode 63; V1 has the same limit.
- **« Press 🌐 key to »** must be « Do Nothing », or every tap also opens the
  emoji picker; a listen-only tap cannot swallow the key. Documented.
- **First syllable**: opening the stream takes a few tens of ms after the
  press; V1 had the same behaviour. The bench's gates and fallback are where
  lost speech is fought; a pre-roll was refused (indicator always on).

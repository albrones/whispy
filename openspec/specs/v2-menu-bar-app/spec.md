# v2-menu-bar-app Specification

## Purpose
Whispy V2's macOS app around the transcription core: V1's trigger key, held or toggled, to dictate; the text delivered to the frontmost app; V1's menu, pill and alerts; and a strict rule that V1 and V2 never both answer the trigger.

## Requirements

### Requirement: The app cannot stay stuck recording
Repeated presses and releases without a matching edge SHALL be ignored; a tap disabled by macOS SHALL be re-enabled within a second and a release missed meanwhile replayed; a recording SHALL be stopped after 5 minutes with its text left on the clipboard instead of pasted; the trigger key pressed together with another key SHALL cancel the dictation it started; a microphone that cannot be opened SHALL return the app to idle and say why in the menu.

#### Scenario: The watchdog stops a forgotten toggle
- **WHEN** a toggled recording reaches 5 minutes
- **THEN** it SHALL be transcribed and its text delivered to the clipboard only

_Tier: unit — `whispy2` `machine`._

#### Scenario: The trigger key as a modifier
- **WHEN** another key goes down while the trigger key is held for a dictation
- **THEN** the recording SHALL be discarded and the following release SHALL start nothing

_Tier: unit — `whispy2` `machine`._

### Requirement: The menu bar shows what the app is doing
The app SHALL show no Dock icon. Its menu SHALL follow V1's structure, top to bottom:
- the header « Whispy · voice dictation »;
- the status line;
- the hidden permission item;
- a separator;
- the « SETTINGS » header;
- Copy to clipboard, Toggle mode, the Trigger submenu titled « Trigger: <key> » with V1's presets, and Start at login;
- a separator;
- Restart;
- Quit (⌘Q).

The status line SHALL be V1's, with a leading brand-green « ● »: « Listening… » while the trigger is down before recording, then « Loading model… », « ⚠ Model not loaded », « Recording », « Transcribing… » and « Ready ». While V2 yields to V1, it SHALL read « Whispy V1 is running — the trigger key is left to it », whichever key the trigger is.

Theming SHALL follow V1:
- toggles show a trailing green ✓ when on;
- submenu choices show a leading green ✓, with an aligned blank when unchecked;
- the SETTINGS header is uppercase, green and letter-spaced;
- the green is #24bf9e on dark menus and #1c9a7f on light menus, re-rendered when the appearance changes.

Restart SHALL relaunch the app once the running instance has released its control socket. Quit SHALL free the models before the process exits.

#### Scenario: Quit exits cleanly
- **WHEN** Quit is chosen after the models are loaded
- **THEN** the process SHALL exit without the whisper.cpp Metal abort

_Tier: manual — launch, then press Quit through the Accessibility API (2026-10-17)._

#### Scenario: The menu matches V1
- **WHEN** the menu is read through the Accessibility API with V2 idle and models loaded
- **THEN** its items SHALL be, in order: « Whispy · voice dictation », « ●  Ready », « SETTINGS », « Copy to clipboard   ✓ », « Toggle mode », « Trigger: Fn », « Start at login », « Restart », « Quit »

_Tier: unit — menu model; manual — Accessibility API read._

#### Scenario: Appearance switch
- **WHEN** the system switches from dark to light appearance
- **THEN** the dot, the header and the check marks SHALL be redrawn in #1c9a7f

_Tier: unit — colour by appearance; manual._

#### Scenario: Restart hands over
- **WHEN** Restart is chosen
- **THEN** a new V2 SHALL answer on the control socket within 10 s and only one V2 process SHALL remain

_Tier: script._

### Requirement: V1 and V2 never both answer the trigger
The app SHALL consider V1 running when 127.0.0.1:9090 accepts a connection or a process runs a `Whispy.app/Contents/MacOS/Whispy` executable, check it before listening to the trigger key and every 2 s after, and while V1 runs it SHALL ignore the trigger key and say « Whispy V1 is running — the trigger key is left to it » in its menu. A dictation under way when V1 appears SHALL finish first. V1 SHALL NOT be stopped or modified.

#### Scenario: Started while V1 runs
- **WHEN** whispy2 is launched while `/Applications/Whispy.app` runs
- **THEN** its menu SHALL read « Whispy V1 is running — the trigger key is left to it » and trigger presses SHALL do nothing

_Tier: unit — `whispy2` `machine`, `v1`; manual — menu read through the Accessibility API (2026-10-17)._

#### Scenario: V1 quits
- **WHEN** V1 stops running while V2 is yielded
- **THEN** V2 SHALL become ready and the next trigger press SHALL start a recording

_Tier: unit — `whispy2` `machine`._

### Requirement: Trigger release to inserted text stays under 1.5 s
For a dictation of at least 5 s of speech, the time from the trigger release to the text handed to the inserter SHALL have a p95 under 1.5 s with the default pipeline.

#### Scenario: Latency end to end
- **WHEN** `cargo test --release -p whispy2 --test latency -- --ignored` replays 6.5–6.8 s reference dictations through the app path, resampled from 48 kHz, with the real models
- **THEN** the p95 from release to delivery SHALL be under 1.5 s (measured 2026-10-17: 0.37 s)

_Tier: bench — `v2/whispy2/tests/latency.rs` (needs the models; ignored in CI)._

### Requirement: A dictation that heard nothing is reported
A dictation of 0.5 s or more whose level stays under V1's noise floor SHALL insert nothing and call no engine. The level is the RMS of a 30 ms window times ten, V1's scale, and the floor is 0.1: no window louder than RMS 0.01. It SHALL play the system failure sound, post V1's « Microphone heard nothing » notification with the input device's name, and put the same text in the menu as the last problem. It SHALL NOT be kept as lost speech.

#### Scenario: A deaf take
- **WHEN** a 3 s dictation's windows never exceed RMS 0.006 on the device « MacBook Pro Microphone »
- **THEN** no engine SHALL be called, nothing SHALL be inserted, and the menu SHALL show « Microphone heard nothing (MacBook Pro Microphone) »

_Tier: unit — controller with a fake capture._

#### Scenario: Quiet speech is not a deaf take
- **WHEN** a 3 s dictation's samples never exceed 0.05 but its windows reach RMS 0.05
- **THEN** it SHALL be transcribed as usual

_Tier: unit._

#### Scenario: A short tap is not a deaf take
- **WHEN** a dictation lasts 0.3 s with no sound
- **THEN** nothing SHALL be reported

_Tier: unit._

### Requirement: Each dictation uses the current default input device
Each dictation SHALL open the system default input device at the moment it starts, so a device change in System Settings applies to the next dictation without a restart.

#### Scenario: Switching to a headset
- **WHEN** the default input changes from the built-in microphone to a headset between two dictations
- **THEN** the second dictation SHALL record from the headset

_Tier: manual._

### Requirement: V2 writes a rotated log file without dictated text
V2 SHALL write its status lines, errors and one line per dictation to `~/.whispy/v2/whispy2.log`, with mode 0600. When the file exceeds 5 MB, it SHALL be renamed to `whispy2.log.1`, replacing the previous copy, and a new file SHALL be started. No log line SHALL contain dictated text.

#### Scenario: Rotation
- **WHEN** a write would take the log over 5 MB
- **THEN** the log SHALL become `whispy2.log.1` and the line SHALL go to a new `whispy2.log`

_Tier: unit — logger on a temporary directory with a small limit._

#### Scenario: Launched from Finder
- **WHEN** V2 is launched as an installed bundle with no terminal
- **THEN** its status lines SHALL be in `~/.whispy/v2/whispy2.log`

_Tier: manual._

### Requirement: Holding the trigger dictates in hold mode
With `trigger_mode` `hold`, V2 SHALL start recording when the configured trigger key goes down while idle. When the key is released 0.3 s or more after the press, it SHALL stop, transcribe with the default pipeline and deliver the text to the frontmost app. A release under 0.3 s SHALL discard the recording, as V1's `min_recording_duration` does. A dictation that yields no text SHALL insert nothing.

#### Scenario: A held dictation is inserted
- **WHEN** the trigger is held for 2 s and released, and the dictation transcribes to « bonjour »
- **THEN** the machine SHALL go recording → transcribing → inserting → idle and the inserter SHALL receive « bonjour »

_Tier: unit — `machine`, `controller`._

#### Scenario: A short press in hold mode is discarded
- **WHEN** the trigger is pressed for 120 ms in hold mode
- **THEN** nothing SHALL be transcribed or inserted, and the machine SHALL be idle

_Tier: unit — `machine`._

### Requirement: Toggle mode starts and stops on presses
With `trigger_mode` `toggle`, a press of the trigger while idle SHALL start recording, and the next press SHALL stop it and start the transcription. Releases SHALL be ignored. The pill SHALL stay up for the whole recording, not only while the key is down.

#### Scenario: Press, speak, press again
- **WHEN** in toggle mode the trigger is pressed, released, and pressed again 9 s later
- **THEN** the recording SHALL run for those 9 s and stop on the second press

_Tier: unit — `machine`._

### Requirement: The trigger is one of V1's keys
The trigger SHALL be the key in V1's `trigger` setting:
- Fn when null (keycode 63);
- one of V1's presets: Right Command (54), Right Option (61) or F13 (105);
- any other single keycode set by hand.

For a modifier key, V2 SHALL read its state from the modifier-flags event of that key. For a non-modifier key such as F13, it SHALL use that key's key-down and key-up events. A key combination string SHALL fall back to Fn, with the note « Trigger combinations are not supported yet; using Fn ».

#### Scenario: Right Command as trigger
- **WHEN** `trigger` is 54 and Right Command is held 2 s then released
- **THEN** a dictation SHALL be recorded and delivered, and Left Command SHALL do nothing

_Tier: unit — event decoding by keycode and flags._

#### Scenario: A combination falls back to Fn
- **WHEN** `trigger` is `"ctrl+shift+space"`
- **THEN** Fn SHALL be the trigger and the menu SHALL show the fallback note

_Tier: unit._

### Requirement: The menu bar title is V1's braille waveform
The status item SHALL show text, with no image: V1's idle frame `⣀⣤⣶⣤`. While the trigger is down, while recording, while transcribing, or while models are loading, it SHALL cycle through V1's 16 `waverows` frames every 90 ms, and SHALL go back to the idle frame afterwards. Frame selection SHALL be a pure function, unit-tested.

#### Scenario: Animation follows activity
- **WHEN** a dictation goes from idle to recording to idle
- **THEN** the title SHALL leave `⣀⣤⣶⣤`, show successive `waverows` frames, and return to `⣀⣤⣶⣤`

_Tier: unit — frame selection; manual — real menu bar._

### Requirement: The recording pill is V1's
During a dictation, V2 SHALL show V1's pill:
- a rounded 168×52 pt window, dark (RGBA 0.07, 0.07, 0.09, 0.92), with 11 brand-green (#24bf9e) bars 5 pt wide, 6 pt apart, 5 to 38 pt tall;
- bar height driven by the input level on V1's scale (block RMS × 10, clamped to 1), smoothed, boosted with V1's curve (level^0.5 × 2, capped at 1), shaped by a symmetric envelope and a per-bar wobble;
- drawn at 30 fps, fading in when shown and out when hidden;
- placed bottom-centre of the main screen's visible frame, 40 pt up.

The pill SHALL show on trigger press, or on recording start in toggle mode, and SHALL hide when the recording stops or a press is discarded. It SHALL ignore the mouse, never take focus, and appear above the active Space, including another app's full-screen Space, on every recording. The pure parts (level curve, bar heights, placement) SHALL be unit-tested.

#### Scenario: Bars follow the voice
- **WHEN** the level goes from 0 to 0.5
- **THEN** the middle bar's height SHALL grow from 5 pt towards 38 pt and the outer bars SHALL stay shorter than the middle one

_Tier: unit — bar-height function._

#### Scenario: Above a full-screen app
- **WHEN** a dictation starts while another app is full screen
- **THEN** the pill SHALL appear over it and that app SHALL keep the focus

_Tier: manual._

### Requirement: V1's alerts are posted as notifications
V2 SHALL post a macOS notification titled « Whispy », with V1's subtitle and message, for each of these events: missing permission, can't type into apps, model failed to load, no microphone available, microphone heard nothing, dictation stopped by the time limit, and model still loading at the end of a dictation. A permission alert SHALL also reveal the « ⚠ Missing permission — fix in System Settings… » menu item. Clicking that item SHALL open the System Settings pane for that permission: Microphone, Input Monitoring, Accessibility or Automation. If notifications are not allowed, the alert SHALL still reach the log and the menu.

#### Scenario: Heard nothing is notified
- **WHEN** a dictation is a deaf take on « MacBook Pro Microphone »
- **THEN** a notification « Microphone heard nothing » SHALL be posted with the device name, and the Basso sound SHALL play

_Tier: unit — alert model; manual — notification seen._

#### Scenario: The permission item opens the right pane
- **WHEN** Input Monitoring is missing at startup and the user clicks the warning item
- **THEN** System Settings SHALL open on Privacy & Security → Input Monitoring

_Tier: unit — URL per permission kind; manual — click._

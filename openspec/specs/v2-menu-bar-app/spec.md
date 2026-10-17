# v2-menu-bar-app Specification

## Purpose
Whispy V2's macOS app around the transcription core: Fn held or tapped to dictate, the text pasted into the frontmost app, a menu bar status, and a strict rule that V1 and V2 never both answer Fn.

## Requirements

### Requirement: Holding Fn dictates and releasing it inserts the text
The app SHALL start recording the default microphone when Fn goes down while it is idle, and when Fn is released 0.3 s or more after the press it SHALL stop recording, transcribe the dictation with the default pipeline, and paste the text into the frontmost app. A dictation that yields no text SHALL insert nothing.

#### Scenario: A held dictation is inserted
- **WHEN** Fn is pressed, held for 2 s and released, and the dictation transcribes to « bonjour »
- **THEN** the machine SHALL go recording → transcribing → inserting → idle and the inserter SHALL receive « bonjour » for pasting

_Tier: unit — `whispy2` `machine`, `controller`._

#### Scenario: Silence inserts nothing
- **WHEN** a dictation transcribes to empty text
- **THEN** nothing SHALL be inserted and the machine SHALL be idle

_Tier: unit — `whispy2` `machine`._

#### Scenario: A real dictation reaches the focused field
- **WHEN** the user holds Fn, says a sentence in a text field and releases Fn, with V1 quit
- **THEN** the sentence SHALL appear in that field

_Tier: `[à l'usage]` — needs the user's keyboard, microphone and Accessibility._

### Requirement: A short tap on Fn toggles a hands-free dictation
A press released less than 0.3 s after it went down SHALL latch the recording; the next press SHALL stop it and start the transcription, and the release that follows SHALL be ignored.

#### Scenario: Tap, speak, press again
- **WHEN** Fn is tapped for 120 ms, then pressed again 9 s later
- **THEN** the recording SHALL continue after the tap and stop on the second press, and its release SHALL change nothing

_Tier: unit — `whispy2` `machine`._

### Requirement: The app cannot stay stuck recording
Repeated presses and releases without a matching edge SHALL be ignored; a tap disabled by macOS SHALL be re-enabled within a second and a release missed meanwhile replayed; a recording SHALL be stopped after 5 minutes with its text left on the clipboard instead of pasted; Fn pressed together with another key SHALL cancel the dictation it started; a microphone that cannot be opened SHALL return the app to idle and say why in the menu.

#### Scenario: The watchdog stops a forgotten toggle
- **WHEN** a toggled recording reaches 5 minutes
- **THEN** it SHALL be transcribed and its text delivered to the clipboard only

_Tier: unit — `whispy2` `machine`._

#### Scenario: Fn as a modifier
- **WHEN** another key goes down while Fn is held for a dictation
- **THEN** the recording SHALL be discarded and the following Fn release SHALL not latch a toggle

_Tier: unit — `whispy2` `machine`._

### Requirement: The menu bar shows what the app is doing
The app SHALL show an icon in the menu bar and no Dock icon; its menu SHALL name the current state (ready, recording, transcribing, inserting, yielded to V1) and the last problem (models missing, Input Monitoring or Accessibility not granted, microphone failure), and SHALL offer Quit, which frees the models before the process exits.

#### Scenario: Quit exits cleanly
- **WHEN** Quit is chosen after the models are loaded
- **THEN** the process SHALL exit without the whisper.cpp Metal abort

_Tier: manual — launch, then press Quit through the Accessibility API (2026-10-17)._

### Requirement: V1 and V2 never both answer Fn
The app SHALL consider V1 running when 127.0.0.1:9090 accepts a connection or a process runs a `Whispy.app/Contents/MacOS/Whispy` executable, check it before listening to Fn and every 2 s after, and while V1 runs it SHALL ignore Fn and say « Whispy V1 is running — Fn is left to it » in its menu. A dictation under way when V1 appears SHALL finish first. V1 SHALL NOT be stopped or modified.

#### Scenario: Started while V1 runs
- **WHEN** whispy2 is launched while `/Applications/Whispy.app` runs
- **THEN** its menu SHALL read « Whispy V1 is running — Fn is left to it » and Fn presses SHALL do nothing

_Tier: unit — `whispy2` `machine`, `v1`; manual — menu read through the Accessibility API (2026-10-17)._

#### Scenario: V1 quits
- **WHEN** V1 stops running while V2 is yielded
- **THEN** V2 SHALL become ready and the next Fn press SHALL start a recording

_Tier: unit — `whispy2` `machine`._

### Requirement: Fn release to inserted text stays under 1.5 s
For a dictation of at least 5 s of speech, the time from Fn release to the text handed to the inserter SHALL have a p95 under 1.5 s with the default pipeline.

#### Scenario: Latency end to end
- **WHEN** `cargo test --release -p whispy2 --test latency -- --ignored` replays 6.5–6.8 s reference dictations through the app path, resampled from 48 kHz, with the real models
- **THEN** the p95 from release to delivery SHALL be under 1.5 s (measured 2026-10-17: 0.37 s)

_Tier: bench — `v2/whispy2/tests/latency.rs` (needs the models; ignored in CI)._

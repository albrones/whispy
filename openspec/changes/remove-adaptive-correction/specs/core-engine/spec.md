## MODIFIED Requirements

### Requirement: Trigger callbacks hand off to a dedicated worker thread

The engine SHALL NOT perform blocking work — audio device start/stop or WAV flush — directly on the
hardware trigger listener's own thread (the macOS `CGEventTap` run-loop thread or the Linux `pynput`
listener thread). Instead, the press/release callbacks registered with the hotkey adapter SHALL only
enqueue a signal onto a dedicated queue; a single dedicated `trigger-worker` thread SHALL consume
that queue in arrival order and perform the actual work (pressed/released notifications, notifier
sounds, and `start_recording()`/`stop_recording()`), preserving the same call order used before this
requirement existed. Because both the macOS and Linux hotkey adapters invoke the same engine-level
callbacks, this handoff SHALL cover both platforms without platform-specific changes to the hotkey
adapters themselves.

#### Scenario: Press callback returns without blocking

- **WHEN** the hotkey adapter invokes the engine's trigger-press callback
- **THEN** the callback SHALL return after only enqueuing the press signal, without starting audio
  recording itself

_Tier: unit-mocked — `test_engine.py` (callback timing/ordering asserted with audio mocked)._

#### Scenario: Release callback returns without blocking

- **WHEN** the hotkey adapter invokes the engine's trigger-release callback
- **THEN** the callback SHALL return after only enqueuing the release signal, without stopping audio
  recording itself

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Press and release are processed in arrival order

- **WHEN** a press signal and a subsequent release signal are enqueued in quick succession
- **THEN** the trigger-worker thread SHALL process the press before the release, matching the order
  the hardware events arrived in

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker preserves the pre-handoff call order on press

- **WHEN** the trigger-worker thread processes a press signal
- **THEN** it SHALL notify pressed listeners, then play the recording-started cue, then call
  `start_recording()`, in that order

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker preserves the pre-handoff call order on release

- **WHEN** the trigger-worker thread processes a release signal
- **THEN** it SHALL notify released listeners, then call `stop_recording()`, and SHALL set the
  transcription stop event only if that call actually transitioned `RECORDING` to `TRANSCRIBING`

_Tier: unit-mocked — `test_engine.py`._

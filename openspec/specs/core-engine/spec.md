# core-engine Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration. Clipboard copy SHALL be disabled by default (`False`). The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk; keys absent from `DEFAULT_CONFIG` — including `model_size`, `language`, `beam_size`, `best_of`, and `auto_detect_min_duration` left behind by an earlier version — SHALL be dropped without raising, so an existing config file keeps loading after the upgrade. When a configuration update changes the `trigger` key, the engine SHALL restart the key listener so the new trigger takes effect without a manual Restart. The engine SHALL apply text cleaning to transcription output before text injection. `save_config` SHALL create the `~/.config/whispy` directory with `0700` permissions and SHALL persist `config.json` with `0600` permissions on every save, including the first save after upgrading from a version that wrote the file without restricting permissions; a failure to set these permissions SHALL be logged but SHALL NOT prevent the config from being saved.

#### Scenario: Legacy keys are dropped, not fatal
- **WHEN** a config file written by a pre-Parakeet version is loaded, carrying `model_size` and `language`
- **THEN** loading SHALL succeed, those keys SHALL NOT appear in the validated config, and the next save SHALL persist the file without them

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Default copy to clipboard is disabled
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use `False` for `copy_to_clipboard`

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Trigger change restarts the listener
- **WHEN** a configuration update changes the `trigger` key
- **THEN** the engine SHALL restart the key listener without requiring a manual Restart

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Restart uses correct entry point
The menu bar "Restart" item SHALL launch the application using the correct entry point file `whispy_daemon.py` located at the project root. The resolution of that path and the check for its existence SHALL be performed by a pure, unit-tested helper independent of the menu bar UI; the menu callback SHALL delegate path resolution to that helper and only then perform the relaunch and quit.

#### Scenario: Restart path resolves to daemon
- **WHEN** the path-resolution helper is invoked
- **THEN** it SHALL return the path to `whispy_daemon.py` at the project root

_Tier: unit-pure — `test_paths.py`, `test_config_validation.py::TestRestartPath`._

#### Scenario: Restart path works from any working directory
- **WHEN** the path-resolution helper is invoked from any current working directory
- **THEN** it SHALL return the same project-root `whispy_daemon.py` path (resolution is independent of cwd)

_Tier: unit-pure — `test_paths.py::test_resolution_is_independent_of_cwd`._

#### Scenario: Missing daemon script is detected before relaunch
- **WHEN** the existence check reports that the resolved script does not exist
- **THEN** the restart action SHALL NOT spawn a process and SHALL surface a "Restart file not found" condition

_Tier: unit-pure (existence check) — `test_paths.py::TestDaemonScriptExists`; the alert/relaunch UI stays manual-ui._

#### Scenario: Restart exits current instance
- **WHEN** the user clicks the "Restart" menu item and the script exists
- **THEN** the application launches the new instance and the current menu bar instance quits

_Tier: manual-ui — relaunch + quit is not unit-testable._

### Requirement: Transcription worker always returns the FSM to IDLE
The transcription worker SHALL, upon receiving a stop signal, always return the
state machine to `IDLE` after handling the recording — whether transcription
produced text, produced no usable text (empty or cleaned-to-empty output), or
raised an error. When streaming is enabled, the stop signal handling SHALL flush
and transcribe the final tail chunk; when disabled, it SHALL transcribe the whole
recording as before. In either mode, a failure in transcription SHALL NOT
terminate the worker thread or leave the system wedged in the `TRANSCRIBING`
state.

#### Scenario: Empty transcription completes the FSM
- **WHEN** the worker is signaled to stop and transcription yields no usable text (empty or cleaned-to-empty)
- **THEN** the worker SHALL call `transcription_complete()` so the FSM returns to `IDLE`

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Transcription error does not wedge the FSM
- **WHEN** transcription raises an exception while the worker is handling a stop signal
- **THEN** the worker SHALL log the error, return the FSM to `IDLE`, and remain alive to handle the next recording

#### Scenario: Streaming tail flush completes the FSM
- **WHEN** streaming is enabled and the worker handles the stop signal for the final tail chunk
- **THEN** the worker SHALL transcribe/inject the tail chunk (if any usable text) and return the FSM to `IDLE`

### Requirement: Custom vocabulary biases transcription
The engine SHALL support an optional `custom_vocabulary` configuration value (a list of words or phrases). Because the transducer backend exposes no decoder-biasing channel, the vocabulary SHALL be applied **after** transcription as near-miss correction during text cleaning, not passed to the transcription call. The engine SHALL NOT pass any prompt, hotword, or vocabulary argument to the transcription call. When the list is empty or absent, cleaning SHALL leave transcription output unchanged.

#### Scenario: Vocabulary reaches cleaning, not the model
- **WHEN** `custom_vocabulary` contains one or more terms and a recording is transcribed
- **THEN** the transcription call SHALL receive no vocabulary argument, and the configured terms SHALL be supplied to the text-cleaning step

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Empty vocabulary changes nothing
- **WHEN** `custom_vocabulary` is empty or absent
- **THEN** cleaning SHALL return the transcription output with only normal whitespace normalization applied

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Invalid vocabulary falls back safely
- **WHEN** `custom_vocabulary` is loaded with a non-list value or with non-string entries
- **THEN** config validation SHALL coerce it to a list containing only the valid string entries (an entirely invalid value becomes an empty list) and SHALL NOT raise

_Tier: unit-pure — `test_config_validation.py`._

### Requirement: Stray trigger release does not start transcription

The engine SHALL set the transcription stop event only when stopping actually transitioned the
system from `RECORDING` to `TRANSCRIBING`, so that any stop request with no active recording — a
trigger release, or a call to `stop_and_wait_for_transcription` (used by e.g. the HTTP `/stop`
endpoint) — is a no-op that starts no transcription of a stale or missing file.

#### Scenario: Release with no active recording

- **WHEN** a trigger release is handled while the system is not recording
- **THEN** the engine SHALL NOT set the stop event and SHALL NOT start transcription of a stale or
  missing file

#### Scenario: Stop request with no active recording

- **WHEN** `stop_and_wait_for_transcription` is called while the system is not recording
- **THEN** the engine SHALL NOT set the stop event, SHALL NOT start transcription of a stale or
  missing file, and SHALL return `None` immediately

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Model-load failure is surfaced
When the transcription model fails to load, the engine SHALL report the failure through the status/notifier callback rather than leaving the model silently unloaded, and the failure SHALL reach an actual UI consumer rather than only being logged. The loader's own contract — one retry, then report — is specified in `asr-backend`.

#### Scenario: Model fails to load
- **WHEN** asynchronous model loading raises (download, SSL, or onnxruntime session error)
- **THEN** the engine SHALL invoke the status/notifier callback with a failure signal so the user is informed, instead of silently returning no text on every subsequent dictation

#### Scenario: Menu bar consumes the model-load-failure callback
- **WHEN** the menu bar application initializes
- **THEN** it SHALL register a handler for `on_model_load_failed` and, when it fires, SHALL post a user-visible notification with actionable guidance (check connectivity, then Restart) — the hook SHALL NOT exist without a UI consumer

_Tier: unit-pure — `test_menu_bar.py::TestAlertWiring::test_init_registers_alert_callbacks`._

### Requirement: Chunk pipeline runs during RECORDING without a composite FSM state
When streaming is enabled, the engine SHALL run chunk transcription and injection
through an ordered pipeline that is active **during** the `RECORDING` state,
without introducing a new state machine state. The state machine SHALL keep
`IDLE → RECORDING → TRANSCRIBING → IDLE` and SHALL keep `RECORDING` as the sole
owner of the recording lifecycle. `TRANSCRIBING` (and therefore `is_transcribing`)
SHALL denote only the final tail flush after trigger release, so existing
status/UI consumers that read `is_recording`/`is_transcribing` are unaffected.

#### Scenario: Chunks transcribe while still recording
- **WHEN** streaming is enabled and chunks are emitted during recording
- **THEN** the engine SHALL transcribe and inject them while the state machine remains in `RECORDING`, without entering `TRANSCRIBING`

#### Scenario: is_transcribing reflects only the tail flush
- **WHEN** the engine is injecting mid-recording chunks
- **THEN** `is_transcribing` SHALL remain false until the trigger-release tail flush

#### Scenario: No new FSM state is introduced
- **WHEN** the streaming pipeline is active
- **THEN** the state machine's set of valid states SHALL remain `IDLE`, `RECORDING`, and `TRANSCRIBING`

### Requirement: Explicitly denied startup permissions are surfaced
`Engine.start()` SHALL probe Microphone, Input Monitoring, Accessibility, and Automation access at startup. Each probe reports one of three states — granted, explicitly denied, or undetermined (the system permission prompt is pending or the probe is unavailable). The engine SHALL fire `on_permission_missing(kind, message)` only for explicit denials; a granted or undetermined result SHALL stay silent, since warning on an undetermined state would be redundant with the OS's own prompt.

#### Scenario: Explicit denial fires with actionable guidance
- **WHEN** a startup permission probe reports an explicit denial (e.g. Microphone or Input Monitoring)
- **THEN** the engine SHALL invoke `on_permission_missing` with the permission's kind and a message naming the System Settings pane to fix it

_Tier: unit-mocked — `test_engine.py::TestPermissionMissingSurfaced::test_explicit_denials_fire_with_kind_and_guidance`._

#### Scenario: Granted or undetermined permissions stay silent
- **WHEN** every startup probe reports either granted or undetermined (no explicit denial)
- **THEN** the engine SHALL NOT invoke `on_permission_missing` for any of them

_Tier: unit-mocked — `test_engine.py::TestPermissionMissingSurfaced::test_granted_and_undetermined_stay_silent`._

### Requirement: Recorded audio is always cleaned up after a transcription attempt
`run_transcription` SHALL delete the recorded WAV file after the transcription attempt completes, regardless of the outcome — successful transcription, an empty/`None` result, the model not being loaded, or a raised exception — so recorded voice audio never outlives the attempt that produced it. The only exception is when there was no recording file to begin with (nothing to clean up).

#### Scenario: WAV is deleted when transcription returns no text
- **WHEN** `run_transcription` completes and the transcription result is `None` or an empty string
- **THEN** the recorded WAV SHALL be deleted

_Tier: unit-mocked — `test_engine.py::TestRunTranscriptionCleanup`._

#### Scenario: WAV is deleted when the model is not loaded
- **WHEN** `run_transcription` runs while `state.model` is `None`
- **THEN** the recorded WAV SHALL be deleted even though no transcription was attempted

_Tier: unit-mocked — `test_engine.py::TestRunTranscriptionCleanup::test_deletes_wav_when_model_not_loaded`._

#### Scenario: WAV is deleted when transcription raises
- **WHEN** the underlying transcription call raises an exception
- **THEN** the recorded WAV SHALL still be deleted, and the exception SHALL propagate to the caller

_Tier: unit-mocked — `test_engine.py::TestRunTranscriptionCleanup::test_deletes_wav_when_transcribe_raises`._

### Requirement: Dictating while the model is still loading is surfaced
When the trigger key is released to end a dictation attempt and the transcription model has not finished loading, the menu bar SHALL raise a "model still loading" notification rather than silently producing no transcription output.

#### Scenario: Trigger release while the model is loading
- **WHEN** the trigger key is released and `state.model is None` while `state.model_loading` is true
- **THEN** the menu bar SHALL queue a "Model still loading" alert notification

_Tier: unit-pure — `test_menu_bar.py::TestFnReleasedModelLoadingAlert::test_queues_alert_while_model_still_loading`._

#### Scenario: No alert once the model is ready
- **WHEN** the trigger key is released and the model has finished loading
- **THEN** no "model still loading" alert SHALL be queued

_Tier: unit-pure — `test_menu_bar.py::TestFnReleasedModelLoadingAlert::test_no_alert_once_model_is_loaded`._

### Requirement: Daemon log file rotates instead of growing unbounded
`whispy_daemon.py` SHALL configure `~/.whispy.log` with size-based rotation (1 MB per file, 3 backups retained) rather than a single unbounded log file.

#### Scenario: Log file reaches the size limit
- **WHEN** `~/.whispy.log` reaches the configured 1 MB size limit
- **THEN** it SHALL be rotated to a backup and a fresh log file SHALL be started, up to 3 retained backups

### Requirement: Trigger callbacks hand off to a dedicated worker thread

The engine SHALL NOT perform blocking work — Accessibility reads for correction detection, audio
device start/stop, or WAV flush — directly on the hardware trigger listener's own thread (the macOS
`CGEventTap` run-loop thread or the Linux `pynput` listener thread). Instead, the press/release
callbacks registered with the hotkey adapter SHALL only enqueue a signal onto a dedicated queue; a
single dedicated `trigger-worker` thread SHALL consume that queue in arrival order and perform the
actual work (correction detection, pressed/released notifications, notifier sounds, and
`start_recording()`/`stop_recording()`), preserving the same call order used before this requirement
existed. Because both the macOS and Linux hotkey adapters invoke the same engine-level callbacks,
this handoff SHALL cover both platforms without platform-specific changes to the hotkey adapters
themselves.

#### Scenario: Press callback returns without blocking

- **WHEN** the hotkey adapter invokes the engine's trigger-press callback
- **THEN** the callback SHALL return after only enqueuing the press signal, without calling
  correction detection or starting audio recording itself

_Tier: unit-mocked — `test_engine.py` (callback timing/ordering asserted with audio/AX mocked)._

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
- **THEN** it SHALL perform correction detection, then notify pressed listeners, then play the
  recording-started cue, then call `start_recording()`, in that order

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker preserves the pre-handoff call order on release

- **WHEN** the trigger-worker thread processes a release signal
- **THEN** it SHALL notify released listeners, then call `stop_recording()`, and SHALL set the
  transcription stop event only if that call actually transitioned `RECORDING` to `TRANSCRIBING`

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Chunk accumulation state is thread-safe

Every access to `_chunk_texts` and `_chunk_any_text` SHALL be guarded by `DictationState.lock`, held only around the field access itself and never across a blocking call (transcription, injection, or a lock wait). These fields are written and read from three different threads: the chunk worker appending recognized chunk text, the transcription worker reading them to assemble and inject, and the FSM recording-entry callback / watchdog forced-recovery resetting them for a new cycle.

#### Scenario: Chunk worker append is lock-guarded

- **WHEN** the chunk worker appends a recognized chunk's text to `_chunk_texts`
- **THEN** it SHALL hold `DictationState.lock` for the append and the `_chunk_any_text` update

_Tier: unit-mocked — `test_engine.py` (lock acquisition asserted via a mock/spy lock)._

#### Scenario: Transcription worker read is lock-guarded

- **WHEN** the transcription worker reads `_chunk_texts`/`_chunk_any_text` to assemble the release
  text and decide whether a success cue is warranted
- **THEN** it SHALL take a lock-guarded snapshot of both fields before releasing the lock and
  performing injection

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Recording-entry reset is lock-guarded

- **WHEN** the FSM enters `RECORDING` and the engine resets `_chunk_texts`/`_chunk_any_text` for the
  new cycle
- **THEN** the reset SHALL be performed under `DictationState.lock`

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Watchdog forced-recovery reset is lock-guarded

- **WHEN** the watchdog force-recovers a wedged FSM and resets `_chunk_texts`/`_chunk_any_text`
- **THEN** the reset SHALL be performed under `DictationState.lock`

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Synchronous stop reuses the background transcription worker

The engine SHALL expose a method (`stop_and_wait_for_transcription`) that stops recording and, only
if that actually transitioned `RECORDING` to `TRANSCRIBING`, hands off to the existing background
transcription worker via `state.stop_event` and waits — bounded by an internal timeout — for a
dedicated completion signal before returning the resulting text. This SHALL be the single code path
used both by the trigger-release flow's asynchronous handling and by any caller needing a synchronous
result (e.g. the HTTP API), so streaming-mode chunk draining/assembly is never reimplemented outside
the worker.

#### Scenario: Streaming mode returns assembled chunk text

- **WHEN** `stop_and_wait_for_transcription` is called while streaming produced one or more chunks
- **THEN** it SHALL wait for the worker to drain the chunk queue and assemble the chunks' text, and
  SHALL return that assembled, injected text

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Nothing was recording is a no-op

- **WHEN** `stop_and_wait_for_transcription` is called while the system is not recording
- **THEN** it SHALL NOT set the transcription stop event and SHALL return `None` immediately,
  without waiting on the completion signal

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker completion unblocks the wait promptly

- **WHEN** the background transcription worker finishes handling the stop signal
- **THEN** it SHALL set the completion signal so a caller blocked in
  `stop_and_wait_for_transcription` returns without waiting for the full timeout

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Watchdog recovery also unblocks a waiter

- **WHEN** the watchdog force-recovers a wedged `TRANSCRIBING` state
- **THEN** it SHALL also set the completion signal, so a caller blocked in
  `stop_and_wait_for_transcription` does not wait out the full timeout after the watchdog already
  resolved the cycle

_Tier: unit-mocked — `test_engine.py`._

### Requirement: The recording time limit preserves transcribed text

The engine SHALL stop a recording gracefully when it reaches the maximum recording duration, rather than discarding it. It SHALL stop audio capture, let the normal drain-and-assemble path produce the transcribed text, and deliver that text to the user. The engine SHALL NOT clear the accumulated chunk text before it has been delivered.

Delivery at the limit SHALL be to the **clipboard** rather than by injection,
because after a recording of this length there is no basis for assuming the
originally focused field is still focused, and typing a long block into an
unknown target is its own failure mode.

The engine SHALL notify the user that the limit was reached and where the text
went, through the same user-visible notification path used for other engine
faults. The limit SHALL NOT be reached silently.

If the graceful stop itself fails, the engine SHALL fall back to the forced
recovery path so the FSM always returns to IDLE.

This requirement supersedes the discard-on-recovery behavior for the RECORDING
state; the forced recovery specified for a wedged FSM remains the fallback and is
unchanged for the TRANSCRIBING state. (Note for sequencing: the watchdog
requirement itself is introduced by the pending `fix-fsm-hang-recovery` change;
this change refines only what happens when its RECORDING bound is reached.)

#### Scenario: Reaching the limit delivers the text

- **WHEN** a recording exceeds the maximum recording duration and transcribed chunk text exists
- **THEN** the engine SHALL stop the recording, place the assembled text on the clipboard, return the FSM to IDLE, and SHALL NOT discard the text

_Tier: unit-mocked — `test_engine.py` (limit injected as a small timeout)._

#### Scenario: Reaching the limit notifies the user

- **WHEN** a recording exceeds the maximum recording duration
- **THEN** the engine SHALL fire a user-facing notification stating that the recording was stopped and that the text is on the clipboard

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: A normal recording is unaffected

- **WHEN** a recording is stopped by the user before the maximum recording duration
- **THEN** no limit handling SHALL run, and the text SHALL be injected normally rather than diverted to the clipboard

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: A failed graceful stop still returns to IDLE

- **WHEN** the graceful stop raises while handling the limit
- **THEN** the engine SHALL fall back to forced recovery and the FSM SHALL end in IDLE

_Tier: unit-mocked — `test_engine.py`._

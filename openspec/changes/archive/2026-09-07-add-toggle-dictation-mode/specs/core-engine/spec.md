## ADDED Requirements

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

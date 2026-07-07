## ADDED Requirements

### Requirement: FSM watchdog recovers from wedged states

The engine SHALL run a watchdog that bounds how long the state machine may
dwell in a non-idle state. When the FSM has been in RECORDING without a release,
or in TRANSCRIBING without completion, for longer than a configured recovery
timeout, the watchdog SHALL force the FSM back to IDLE, re-notify status
listeners (so the menu bar returns to "Ready"), and log the forced recovery with
the state it recovered from. The watchdog SHALL NOT interrupt a normal in-progress
transcription that is still making progress; the timeout SHALL be generous enough
to exceed a legitimate long recording/transcription.

#### Scenario: Stuck in RECORDING is recovered

- **WHEN** the FSM has been in RECORDING for longer than the recovery timeout with no release event
- **THEN** the watchdog SHALL force-transition the FSM to IDLE, re-notify status, and log the recovery

#### Scenario: Stuck in TRANSCRIBING is recovered

- **WHEN** the FSM has been in TRANSCRIBING for longer than the recovery timeout with no completion
- **THEN** the watchdog SHALL force-transition the FSM to IDLE, re-notify status, and log the recovery

#### Scenario: Normal cycle is not interrupted

- **WHEN** a recording and transcription complete within the recovery timeout
- **THEN** the watchdog SHALL take no action and the normal RECORDING → TRANSCRIBING → IDLE cycle SHALL proceed unchanged

### Requirement: Forced recovery transition to IDLE

The state machine SHALL expose a way to force the state to IDLE from any state
for recovery purposes, independent of the normal allowed-transition guards, so
the watchdog can unstick a wedged FSM. The forced transition SHALL notify
state-change callbacks like any other transition.

#### Scenario: Force to IDLE from RECORDING

- **WHEN** the watchdog forces recovery while the FSM is in RECORDING
- **THEN** the FSM SHALL become IDLE and fire its state-change callbacks

#### Scenario: Force to IDLE from TRANSCRIBING

- **WHEN** the watchdog forces recovery while the FSM is in TRANSCRIBING
- **THEN** the FSM SHALL become IDLE and fire its state-change callbacks

## ADDED Requirements

### Requirement: Hardware Event Detection
The listener SHALL monitor hardware-level events (specifically the Fn key) and notify the core engine of state changes.

#### Scenario: Fn Key Press (Start Recording)
- **WHEN** a hardware event corresponding to the Fn key is detected with the appropriate flags
- **THEN** the listener SHALL trigger a "start recording" event to the core engine

#### Scenario: Fn Key Release (Stop Recording)
- **WHEN** a hardware event corresponding to theFn key release is detected
- **THEN** the listener SHALL trigger a "stop recording" event to the core engine

### Requirement: Event Loop Integration
The listener SHALL run in a dedicated, non-blocking thread to ensure hardware events are captured reliably without interfering with the UI or core engine.

#### Scenario: Continuous Listening
- **WHEN** the system is running
- **THEN** the listener SHALL maintain an active event tap to capture keystrokes in real-time

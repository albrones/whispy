# event-listener Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements
### Requirement: Hardware Event Detection
The listener SHALL monitor hardware-level events (specifically the Fn key) and notify the core engine of state changes.

#### Scenario: Fn Key Press (Start Recording)
- **WHEN** a hardware event corresponding to the Fn key is detected with the appropriate flags
- **THEN** the listener SHALL trigger a "start recording" event to the core engine

_Tier: macos-real — `test_event_tap_e2e.py` exercises this with Quartz MOCKED, so a green run does NOT prove the real event tap fires. Real-seam coverage deferred to step A; pure flag-decoding logic extractable in step C._

#### Scenario: Fn Key Release (Stop Recording)
- **WHEN** a hardware event corresponding to theFn key release is detected
- **THEN** the listener SHALL trigger a "stop recording" event to the core engine

_Tier: macos-real — same caveat: Quartz mocked in CI. Deferred to step A._

### Requirement: Event Loop Integration
The listener SHALL run in a dedicated, non-blocking thread to ensure hardware events are captured reliably without interfering with the UI or core engine.

#### Scenario: Continuous Listening
- **WHEN** the system is running
- **THEN** the listener SHALL maintain an active event tap to capture keystrokes in real-time

_Tier: macos-real — requires a live CGEventTap; not verifiable in CI. Deferred to step A._

### Requirement: Pure trigger-event decoding
The decision of whether a keyboard event represents a trigger-key press, a trigger-key release, or is irrelevant SHALL be computed by a pure function of `(event_type, keycode, flags, trigger_keycode)` that does not depend on the live event tap. The function SHALL handle the Fn-key secondary-flag convention (keycode 63: flag set = press, flag clear = release) and SHALL unwrap the pyobjc tuple form of the flags value. Keycode-to-name resolution SHALL likewise be a pure function. The event-tap callback SHALL delegate to these functions.

#### Scenario: Fn press decoded
- **WHEN** the decode function receives a flags-changed event for keycode 63 with the secondary-Fn flag set
- **THEN** it SHALL return "press"

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Fn release decoded
- **WHEN** the decode function receives a flags-changed event for keycode 63 with the secondary-Fn flag clear
- **THEN** it SHALL return "release"

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Flags tuple form is unwrapped
- **WHEN** the flags value arrives as a tuple (pyobjc legacy form)
- **THEN** the decode function SHALL use its first element and decode correctly rather than misread the whole tuple

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Non-trigger keycode ignored
- **WHEN** the decode function receives an event whose keycode is not the trigger keycode
- **THEN** it SHALL return none (no press, no release)

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Keycode maps to human-readable name
- **WHEN** `keycode_to_name` receives a known keycode (e.g. 63)
- **THEN** it SHALL return the mapped name, and SHALL return a `keyNN` fallback for unknown keycodes

_Tier: unit-pure — `test_event_decode.py`._


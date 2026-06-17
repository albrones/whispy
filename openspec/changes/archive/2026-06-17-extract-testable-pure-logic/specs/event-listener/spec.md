## ADDED Requirements

### Requirement: Pure trigger-event decoding
The decision of whether a keyboard event represents a trigger-key press, a trigger-key release, or is irrelevant SHALL be computed by a pure function of `(event_type, keycode, flags, trigger_keycode)` that does not depend on the live event tap. The function SHALL handle the Fn-key secondary-flag convention (keycode 63: flag set = press, flag clear = release) and SHALL unwrap the pyobjc tuple form of the flags value. Keycode-to-name resolution SHALL likewise be a pure function. The event-tap callback SHALL delegate to these functions.

#### Scenario: Fn press decoded
- **WHEN** the decode function receives a flags-changed event for keycode 63 with the secondary-Fn flag set
- **THEN** it SHALL return "press"

_Tier: unit-pure._

#### Scenario: Fn release decoded
- **WHEN** the decode function receives a flags-changed event for keycode 63 with the secondary-Fn flag clear
- **THEN** it SHALL return "release"

_Tier: unit-pure._

#### Scenario: Flags tuple form is unwrapped
- **WHEN** the flags value arrives as a tuple (pyobjc legacy form)
- **THEN** the decode function SHALL use its first element and decode correctly rather than misread the whole tuple

_Tier: unit-pure._

#### Scenario: Non-trigger keycode ignored
- **WHEN** the decode function receives an event whose keycode is not the trigger keycode
- **THEN** it SHALL return none (no press, no release)

_Tier: unit-pure._

#### Scenario: Keycode maps to human-readable name
- **WHEN** `keycode_to_name` receives a known keycode (e.g. 63)
- **THEN** it SHALL return the mapped name, and SHALL return a `keyNN` fallback for unknown keycodes

_Tier: unit-pure._

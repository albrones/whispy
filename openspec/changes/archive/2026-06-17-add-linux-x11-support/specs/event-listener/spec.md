## MODIFIED Requirements

### Requirement: Hardware Event Detection
The listener SHALL monitor hardware-level keyboard events for a **configurable trigger key** and notify the core engine of state changes. The trigger SHALL default to the Fn key on macOS (preserving current behavior) and to a documented push-to-talk key on Linux. The trigger SHALL be resolvable from configuration.

#### Scenario: Trigger Press (Start Recording)
- **WHEN** a hardware event corresponding to the configured trigger key is detected as a press
- **THEN** the listener SHALL trigger a "start recording" event to the core engine

_Tier: platform-real — Quartz mocked on macOS, X11 session required on Linux; green in CI does NOT prove the real seam fires._

#### Scenario: Trigger Release (Stop Recording)
- **WHEN** a hardware event corresponding to the configured trigger key is detected as a release
- **THEN** the listener SHALL trigger a "stop recording" event to the core engine

_Tier: platform-real — same caveat; real seam deferred to the per-OS smoke tier._

#### Scenario: macOS default is Fn
- **WHEN** no trigger override is configured on macOS
- **THEN** the listener SHALL use the Fn key (keycode 63) as the trigger, unchanged from prior behavior

_Tier: unit-pure — default resolution verifiable without a live tap._

### Requirement: Pure trigger-event decoding
The decision of whether a keyboard event represents a trigger-key press, a trigger-key release, or is irrelevant SHALL be computed by a pure function that does not depend on any live event source. The function SHALL support two decode paths: the macOS Fn-key secondary-flag convention (keycode 63: flag set = press, flag clear = release, unwrapping the pyobjc tuple form of the flags value) **and** a platform-neutral key-match path where a configured key/combo maps key-down to "press" and key-up to "release". Keycode-to-name resolution SHALL likewise be a pure function. The OS-shell callbacks (macOS event tap and Linux listener) SHALL delegate to these functions.

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

#### Scenario: Configured key match decoded
- **WHEN** the decode function receives a key-down for the configured trigger key on the key-match path
- **THEN** it SHALL return "press", and SHALL return "release" for the corresponding key-up

_Tier: unit-pure — `test_event_decode.py` (new key-match cases)._

#### Scenario: Non-trigger keycode ignored
- **WHEN** the decode function receives an event whose key is not the configured trigger
- **THEN** it SHALL return none (no press, no release)

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Keycode maps to human-readable name
- **WHEN** `keycode_to_name` receives a known keycode (e.g. 63)
- **THEN** it SHALL return the mapped name, and SHALL return a `keyNN` fallback for unknown keycodes

_Tier: unit-pure — `test_event_decode.py`._

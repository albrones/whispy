## ADDED Requirements

### Requirement: Trigger mode selects hold or toggle semantics

The system SHALL support two trigger modes, resolved from a `trigger_mode`
configuration value. In **hold** mode (the default, and the current behavior) a
trigger press starts recording and the matching trigger release stops it. In
**toggle** mode a trigger press starts recording, the next trigger press stops
it, and a trigger release SHALL NOT stop recording.

The mode SHALL be applied in the engine's trigger-event worker — the single
consumer shared by both platform listeners — so that macOS and Linux derive the
behavior from one implementation and the platform listeners keep emitting the
same press/release vocabulary regardless of mode.

Changing the mode SHALL take effect without restarting the application.

#### Scenario: Toggle press starts recording

- **WHEN** the trigger is pressed in toggle mode while the FSM is IDLE
- **THEN** recording SHALL start, exactly as a hold-mode press does

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Second toggle press stops recording

- **WHEN** the trigger is pressed in toggle mode while the FSM is RECORDING
- **THEN** recording SHALL stop and transcription SHALL be signalled, as a hold-mode release does

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Toggle release does not stop recording

- **WHEN** the trigger is released in toggle mode while the FSM is RECORDING
- **THEN** the FSM SHALL remain in RECORDING

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Hold mode is unchanged

- **WHEN** the trigger is pressed and released in hold mode
- **THEN** recording SHALL start on the press and stop on the release, with no observable difference from the behavior before this change

_Tier: unit-mocked — `test_engine.py` (existing tests must pass unmodified)._

#### Scenario: Mode change applies without a restart

- **WHEN** `trigger_mode` is changed while the application is running
- **THEN** the next trigger press SHALL follow the new mode

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Toggle mode keeps the trigger-held flag accurate

In toggle mode the physical trigger release SHALL still clear the engine's
trigger-held state, even though it no longer stops recording. The bounded wait
that defers injection until the trigger is physically released depends on this
flag; leaving it set would delay every injection by the full timeout and, because
streaming mode injects almost immediately after the stopping press, would allow a
still-held modifier to mangle the injected characters into their modifier-layer
variants.

In toggle mode the engine SHALL NOT emit a trigger-release event to its
subscribers when the key is physically released, because the recording is still
running: subscribers treat that event as the end of the dictation. The trigger's
physical state SHALL be tracked on every press and release, including the press
that stops the recording, which arrives with the keys still held.

#### Scenario: Held flag clears on release in toggle mode

- **WHEN** the trigger is pressed and then released in toggle mode
- **THEN** the trigger-held flag SHALL be clear, and the pre-injection wait SHALL return immediately rather than blocking for its timeout

_Tier: unit-pure — `test_engine.py` (flag state asserted directly, no live listener)._

#### Scenario: Releasing the key mid-dictation does not end the dictation for subscribers

- **WHEN** the trigger is released in toggle mode while recording continues
- **THEN** no trigger-release event SHALL reach subscribers, so a UI showing recording state (the waveform pill) SHALL remain visible until the recording actually stops

_Tier: unit-mocked — `test_engine.py` / `test_menu_bar.py`._

#### Scenario: The stopping press is still held

- **WHEN** the press that stops a toggle-mode recording is handled
- **THEN** the trigger SHALL still be recorded as held, so the pre-injection wait defers typing until the keys are physically lifted

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Modifier-combination triggers

The trigger SHALL be expressible as a modifier combination in addition to a
single key. A combination SHALL be configured in a canonical string form —
lowercase, `+`-separated, in the fixed order `ctrl+alt+cmd+shift+<key>` — and
SHALL be translated to a platform match by a pure function, with no live event
source involved. A combination SHALL match only when the trigger key matches
**and** every required modifier is simultaneously held; a partial modifier set
SHALL NOT match. An unparseable combination SHALL resolve to the platform default
trigger rather than disabling trigger detection.

Single-key triggers SHALL continue to decode exactly as before: a zero required-
modifier set SHALL reproduce the existing behavior.

#### Scenario: Combination parses to a keycode and mask

- **WHEN** the pure parser receives `"ctrl+alt+cmd+e"`
- **THEN** it SHALL return the E keycode and a mask containing the Control, Option and Command bits

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: All required modifiers must be held

- **WHEN** the decoder receives the combination's trigger key with only some of the required modifier bits set
- **THEN** it SHALL return none (no press, no release)

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Complete combination decodes as a press

- **WHEN** the decoder receives the combination's trigger key with every required modifier bit set
- **THEN** it SHALL return "press"

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Unparseable combination falls back to the platform default

- **WHEN** the configured trigger is a string that does not parse as a key or combination
- **THEN** the listener SHALL use the platform default trigger and SHALL remain active

_Tier: unit-pure — `test_event_decode.py` / `test_engine.py`._

#### Scenario: Single-key decoding is unaffected

- **WHEN** the decoder is used with no required modifiers
- **THEN** every existing single-key press/release case SHALL decode as it did before this change

_Tier: unit-pure — `test_event_decode.py` (existing cases must pass unmodified)._

#### Scenario: Linux combination match uses tracked modifier state

- **WHEN** the Linux listener receives the combination's trigger key while it has recorded every required modifier as held
- **THEN** the pure key-match decode SHALL return "press", and SHALL return none if any required modifier is not held

_Tier: unit-pure — `test_event_decode.py`; the modifier tracking itself is platform-real._

### Requirement: Combination trigger names resolve correctly

The keycode-to-name table SHALL resolve correctly for every key a shipped trigger
preset names, so logs and the menu's fallback label are accurate.

#### Scenario: Preset letter keycodes resolve to their letters

- **WHEN** the decoder resolves the name for the keycode used by a shipped combination preset
- **THEN** it SHALL return that key's actual letter

_Tier: unit-pure — `test_event_decode.py`._

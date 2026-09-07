# event-listener Specification

## Purpose
Hardware-level trigger-key detection and the pure event-decoding logic behind it.
The trigger is configurable (Fn keycode default on macOS, a push-to-talk key on
Linux/X11); the macOS CGEventTap and Linux pynput shells delegate the press/release
decision to pure decode functions.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements

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

### Requirement: Event Loop Integration
The listener SHALL run in a dedicated, non-blocking thread to ensure hardware events are captured reliably without interfering with the UI or core engine.

#### Scenario: Continuous Listening
- **WHEN** the system is running
- **THEN** the listener SHALL maintain an active event tap to capture keystrokes in real-time

_Tier: macos-real — requires a live CGEventTap; not verifiable in CI. Deferred to step A._

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

### Requirement: Trigger decoding names the default trigger correctly
The trigger-event decoder SHALL map the default trigger keycode (63) to the name `"fn"`, so logs and UI that display the trigger name are accurate.

#### Scenario: Default trigger keycode resolves to fn
- **WHEN** the decoder resolves the name for keycode 63
- **THEN** it SHALL return `"fn"` (and SHALL NOT return `"f5"`, which is keycode 96)

### Requirement: Modifier-key triggers emit a release
For a configured trigger that arrives as a modifier (`flags_changed`) event, the decoder SHALL emit both a press and a matching release derived from the modifier flag state, so recording stops when the key is released.

#### Scenario: Modifier trigger press then release
- **WHEN** a configured modifier trigger is pressed and then released
- **THEN** the decoder SHALL emit a `press` on the down transition and a `release` on the up transition (not a perpetual `press`)

### Requirement: Event tap recovers from OS disablement and callback errors
The macOS event tap SHALL re-arm itself when the OS disables it, and SHALL contain exceptions raised by trigger callbacks, so the hotkey keeps working for the whole session.

#### Scenario: OS disables the tap
- **WHEN** the tap receives `kCGEventTapDisabledByTimeout` or `kCGEventTapDisabledByUserInput`
- **THEN** it SHALL re-enable the tap and continue delivering events

#### Scenario: A trigger callback raises
- **WHEN** a trigger press/release callback raises an exception
- **THEN** the tap SHALL log and continue, and SHALL NOT let the exception disable the tap or kill the listener thread

### Requirement: Event-tap failure guidance matches the current architecture
When `CGEventTapCreate` fails or the run loop does not start in time, the listener's stderr guidance SHALL name Whispy and the in-app Restart action (or `open -a Whispy`), and SHALL NOT reference `python3` or the pre-rebrand `com.whispy` LaunchAgent, since the shipped macOS install is a signed `.app` bundle with no LaunchAgent.

#### Scenario: Tap creation fails
- **WHEN** `CGEventTapCreate` returns `None`
- **THEN** the printed guidance SHALL tell the user to grant Input Monitoring to Whispy and restart via the menu's Restart item or `open -a Whispy`, not `python3` or `launchctl kickstart`

#### Scenario: Run loop start times out
- **WHEN** the run loop does not confirm startup within the timeout
- **THEN** the printed guidance SHALL name Whispy, not `python3`, as the process that may be missing Input Monitoring

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

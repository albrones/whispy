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

For a modifier trigger whose physical key has a known device-dependent flag bit (the bit macOS sets for that specific key, distinct from the side-agnostic modifier mask), press and release SHALL be derived from that bit on the **current** event alone: set means press, clear means release. The decode SHALL NOT depend on flags observed on any previous event, so no missed, reordered, or synthetic event can leave the trigger stuck in a state from which no further press is recognised.

The flag-diff against previously observed flags is retained only as the fallback for a modifier trigger with no known device-dependent bit.

#### Scenario: Modifier trigger press then release
- **WHEN** a configured modifier trigger is pressed and then released
- **THEN** the decoder SHALL emit a `press` on the down transition and a `release` on the up transition (not a perpetual `press`)

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Press decoded from the device-dependent bit alone
- **WHEN** the decoder receives a `flags_changed` event for a modifier trigger with a known device-dependent bit, that bit set, and previously observed flags that already carried the side-agnostic modifier mask
- **THEN** it SHALL return `press`

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: The opposite-side key of the same modifier does not strand the trigger
- **WHEN** the key on the other side of the keyboard sharing the trigger's side-agnostic modifier mask (for example Left Option against a Right Option trigger) is held across the trigger's press
- **THEN** the decoder SHALL still return `press` for the trigger's own event, so a toggle-mode recording can be stopped

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: A missed modifier event does not strand the trigger
- **WHEN** a `flags_changed` event for the trigger is not delivered, and the next delivered event for the trigger carries its device-dependent bit set
- **THEN** the decoder SHALL return `press` rather than none, so recovery needs no resynchronisation step

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: A modifier with no known device bit still decodes
- **WHEN** the configured modifier trigger has no known device-dependent bit
- **THEN** the decoder SHALL fall back to the flag-diff against previously observed flags and decode press and release as before

_Tier: unit-pure — `test_event_decode.py`._

### Requirement: An undecodable trigger event is reported
An event carrying the configured trigger keycode that the decoder resolves to neither a press nor a release SHALL be reported to the daemon log at WARNING, rate-limited so a repeating condition cannot flood the log. A trigger that stops responding SHALL leave evidence in the log rather than be diagnosable only by the absence of subsequent lines.

#### Scenario: Trigger event decodes to nothing
- **WHEN** the listener receives an event whose keycode matches the configured trigger and the decoder returns neither `press` nor `release`
- **THEN** the listener SHALL log the occurrence at WARNING with the event kind and the observed modifier flags

_Tier: unit — `test_event_tap.py`._

#### Scenario: A repeating undecodable condition does not flood the log
- **WHEN** undecodable trigger events arrive repeatedly
- **THEN** the listener SHALL bound how often it logs them, so the daemon log stays readable

_Tier: unit — `test_event_tap.py`._

#### Scenario: Events for other keys are not reported
- **WHEN** the listener receives an event whose keycode does not match the configured trigger
- **THEN** it SHALL NOT log an undecodable-trigger warning

_Tier: unit — `test_event_tap.py`._

### Requirement: A trigger keycode is named as the key it actually is
The name the application shows for a trigger keycode SHALL be the name of that
physical key on macOS, as published in Carbon's `<HIToolbox/Events.h>`. That
name reaches the user in the menu bar's trigger item and in the daemon log, and
it is the same table a hand-written string trigger is resolved through, so a
wrong entry both misreports the configured trigger and binds a different key
than the one named.

Distinct keycodes SHALL NOT share a name, because the reverse lookup that
resolves a string trigger would otherwise bind whichever entry came last.

#### Scenario: A modifier trigger is named as a modifier
- **WHEN** the configured trigger is a right-hand modifier keycode, such as Right Option
- **THEN** the name shown for it SHALL be that modifier, not a function key

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: Every trigger preset resolves to its own name
- **WHEN** each keycode offered as a trigger preset is converted to a name
- **THEN** each SHALL yield the name of that key, and no two keycodes in the table SHALL share a name

_Tier: unit-pure — `test_event_decode.py`._

#### Scenario: A name resolves back to the keycode it came from
- **WHEN** any name in the table is parsed as a string trigger
- **THEN** it SHALL resolve to the keycode that produced it

_Tier: unit-pure — `test_event_decode.py`._

### Requirement: Event tap recovers from OS disablement and callback errors
The macOS event tap SHALL re-arm itself when the OS disables it, and SHALL contain exceptions raised by trigger callbacks, so the hotkey keeps working for the whole session.

Recovery SHALL NOT depend on the listener receiving the disablement event. The
disablement notification is delivered through the very tap whose health is in
question, and it is delivered once; a recovery path reachable only through that
channel leaves the trigger key permanently dead whenever the notification is
missed or the re-enable does not take. The listener SHALL therefore also verify
tap liveness on a bounded recurring interval and re-enable a tap it finds
disabled, independently of any event arriving.

Both recovery paths SHALL be retained. The event-driven path recovers faster and
carries the disablement *reason*, which the liveness check cannot observe and
which is the evidence needed to attribute recurring disablements to a cause.

Every recovery SHALL be recorded in the daemon log (`~/.whispy.log`) at WARNING
level, so that a re-arm is correlatable against the `[fsm]` and `[audio]` lines
around it and so that recurrence is countable rather than invisible. A recovery
SHALL NOT be reported only to a stream that is discarded when Whispy runs as a
GUI `.app`.

#### Scenario: OS disables the tap
- **WHEN** the tap receives `kCGEventTapDisabledByTimeout` or `kCGEventTapDisabledByUserInput`
- **THEN** it SHALL re-enable the tap, continue delivering events, and record the recovery and its reason in the daemon log at WARNING

_Tier: unit-mocked — `test_event_tap_e2e.py` (Quartz mocked)._

#### Scenario: The tap is disabled without a disablement event reaching the listener
- **WHEN** the tap is disabled and no `kCGEventTapDisabledByTimeout` / `kCGEventTapDisabledByUserInput` event is delivered to the callback
- **THEN** the periodic liveness check SHALL observe the disabled tap within its interval, re-enable it, and record the recovery in the daemon log at WARNING

_Tier: unit-mocked — `test_event_tap_e2e.py` (liveness probe driven directly, Quartz mocked)._

#### Scenario: A healthy tap is not repeatedly re-enabled
- **WHEN** the liveness check runs against a tap that is enabled
- **THEN** it SHALL NOT re-enable the tap and SHALL NOT emit a recovery log line

_Tier: unit-mocked — `test_event_tap_e2e.py`._

#### Scenario: The trigger key still works after a disablement during live typing
- **WHEN** a toggle-mode dictation with live typing enabled runs long enough for the OS to disable the tap
- **THEN** the trigger key SHALL still stop the recording afterwards without restarting the app, and `~/.whispy.log` SHALL contain the recovery line

_Tier: macos-real — requires a real event tap and real synthetic keystroke injection._

#### Scenario: A trigger callback raises
- **WHEN** a trigger press/release callback raises an exception
- **THEN** the tap SHALL log and continue, and SHALL NOT let the exception disable the tap or kill the listener thread

_Tier: unit-mocked — `test_event_tap_e2e.py`._

### Requirement: A tap recovery during a toggle-mode recording is reported, not guessed at
When the tap is re-armed while the dictation state machine is in RECORDING and
the active trigger mode is `toggle`, the system SHALL report that a stop-press
may have been lost during the outage, in the daemon log at WARNING.

The system SHALL NOT synthesize a press to resolve this condition. In toggle
mode a press means *stop the recording*, and whether one occurred while the tap
was disabled is an edge that cannot be reconstructed from state after the fact.
A synthesized press would end a dictation the user is still speaking into,
turning a recoverable annoyance into lost speech.

This is deliberately asymmetric with the existing missed-**release** recovery,
which remains unchanged: a release is verifiable against the live modifier flag
state, and a spurious one only ends a recording the user had already ended.

#### Scenario: Re-arm during a toggle-mode recording
- **WHEN** the tap is re-enabled (by either recovery path) while the state machine is in RECORDING and the trigger mode is `toggle`
- **THEN** the system SHALL record at WARNING that a stop-press may have been lost, and SHALL leave the state machine in RECORDING

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Re-arm while idle is not reported as a lost press
- **WHEN** the tap is re-enabled while the state machine is in IDLE
- **THEN** the system SHALL record the recovery itself but SHALL NOT report a possibly-lost stop-press

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Hold-mode release recovery is unchanged
- **WHEN** the tap is re-enabled while the trigger mode is `hold` and the trigger modifier is no longer physically held
- **THEN** the existing missed-release recovery SHALL still emit the release and stop the recording, exactly as before this change

_Tier: unit-mocked — `test_event_tap_e2e.py`._

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

## MODIFIED Requirements

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

## ADDED Requirements

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

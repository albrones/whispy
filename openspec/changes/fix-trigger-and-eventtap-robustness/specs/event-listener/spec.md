## ADDED Requirements

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

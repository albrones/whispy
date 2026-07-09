## MODIFIED Requirements

### Requirement: Event tap recovers from OS disablement and callback errors

The macOS event tap SHALL re-arm itself when the OS disables it, and SHALL contain exceptions raised by trigger callbacks, so the hotkey keeps working for the whole session. Because a modifier trigger's press/release is decoded from `flags_changed` transitions, re-arming alone is not sufficient: a release that fired while the tap was disabled is lost and the tracked previous-flags state is left stale. On re-arm the listener SHALL re-sync its tracked modifier-flag state from the live keyboard modifier state, so the next transition decodes correctly. If, after re-arm, the trigger modifier is no longer held while recording is active, the listener SHALL emit the missed release so the engine cannot remain stuck in RECORDING.

#### Scenario: OS disables the tap

- **WHEN** the tap receives `kCGEventTapDisabledByTimeout` or `kCGEventTapDisabledByUserInput`
- **THEN** it SHALL re-enable the tap and continue delivering events

#### Scenario: Release missed during disablement is recovered

- **WHEN** the tap was disabled while a modifier trigger was held, the user released it during the outage, and the tap is then re-armed
- **THEN** the listener SHALL re-sync its tracked flag state and emit the missed `release` so recording stops

#### Scenario: Flag state re-synced so next press decodes correctly

- **WHEN** the tap re-arms after an outage
- **THEN** the tracked previous-flags value SHALL reflect the live modifier state, so the next modifier transition is decoded as a correct press/release rather than an inverted one

## ADDED Requirements

### Requirement: Visualization platform availability
The floating overlay visualization window SHALL be a macOS-only surface. On Linux (v1), the overlay SHALL NOT be required; recording state SHALL be conveyed through the tray UI instead, and the absence of the overlay SHALL NOT affect the recording lifecycle. Audio-level monitoring and the engine's RECORDING/TRANSCRIBING transitions SHALL behave identically across platforms regardless of overlay presence.

#### Scenario: Overlay shown on macOS
- **WHEN** recording starts on macOS
- **THEN** the floating overlay window SHALL appear as today

_Tier: macos-real — requires AppKit; not verifiable in CI._

#### Scenario: No overlay on Linux, lifecycle intact
- **WHEN** recording starts on Linux v1
- **THEN** no overlay window SHALL be required, the tray SHALL reflect the recording state, and the audio-level monitor and state transitions SHALL run unchanged

_Tier: linux-real — deferred to a Linux smoke run._

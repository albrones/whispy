## ADDED Requirements

### Requirement: Real microphone capture produces a valid recording
The system SHALL, when driven against the real default input device, produce a valid 16 kHz mono WAV recording. Verification SHALL run the real `AudioEngine` start/stop cycle and assert the output file is readable as WAV with the expected rate and channel count and exceeds the readiness size threshold. It SHALL skip cleanly when `sox` or an input device is unavailable.

#### Scenario: Recording yields a valid WAV
- **WHEN** the real audio engine records for a short interval against the default device
- **THEN** the output SHALL be a WAV file at 16 kHz mono whose size exceeds the readiness threshold

_Tier: macos-real — `@pytest.mark.macos`; skips without `sox`/input device._

### Requirement: Real osascript clipboard automation works
The system SHALL be able to set and read the system clipboard via the same `osascript` automation that text injection depends on. Verification SHALL set a unique token on the clipboard via real `osascript` and read it back with `pbpaste`.

#### Scenario: Clipboard round-trips through osascript
- **WHEN** a unique token is written to the clipboard via real `osascript` and read back with `pbpaste`
- **THEN** the read-back value SHALL equal the token

_Tier: macos-real — `@pytest.mark.macos`. The Cmd+V paste into a focused field stays operator-verified (out of unattended scope)._

### Requirement: Live event tap arms with permission
The system SHALL be able to arm a real `CGEventTap` when Input Monitoring is granted. Verification SHALL start a real `EventTapListener` in a subprocess (so the suite's global `Quartz` mock does not apply) and assert it reports active; it SHALL skip when Input Monitoring is not granted.

#### Scenario: Event tap becomes active when permission is granted
- **WHEN** a real `EventTapListener` is started in a subprocess with real Quartz and Input Monitoring granted
- **THEN** the listener SHALL report `active` true

_Tier: macos-real — `@pytest.mark.macos`; skips when permission is absent or `CGEventTapCreate` returns no tap._

## ADDED Requirements

### Requirement: Live-drive record→transcribe cycle over HTTP (macOS)
The system SHALL verify, on a real Mac, that the running daemon performs a full record→transcribe cycle when driven over its HTTP API. Verification SHALL boot the real daemon, poll `GET /status` for readiness, drive `POST /start` then `POST /stop` (or `/stop-async` with polling), and assert the status transitions are valid and `GET /last-transcription` returns non-empty, well-formed text. It SHALL report UNVERIFIED — never silent pass — when the microphone, model, or required permission is unavailable.

#### Scenario: driven cycle yields a transcription on macOS
- **WHEN** the real daemon is booted on macOS and driven through `POST /start` → speak/record → `POST /stop` → `GET /last-transcription`
- **THEN** the status SHALL transition through recording to idle and the last transcription SHALL be non-empty and well-formed

#### Scenario: missing mic/model surfaces as UNVERIFIED on macOS
- **WHEN** the microphone, model, or permission is unavailable during the driven cycle
- **THEN** the result SHALL be reported as UNVERIFIED, not as a pass

_Tier: live-driven — real daemon driven over HTTP against real mic + model; unattended; runs under `-m macos`._

### Requirement: Live-drive record→transcribe cycle over HTTP (Linux/X11)
The system SHALL verify, on a real Linux/X11 session, that the running daemon performs a full record→transcribe cycle when driven over its HTTP API, with the same drive sequence and assertions as the macOS scenario. It SHALL report UNVERIFIED when the microphone, model, `xdotool`, or X11 session is unavailable, and SHALL skip Wayland sessions (Whispy v1 is X11-only).

#### Scenario: driven cycle yields a transcription on Linux/X11
- **WHEN** the real daemon is booted under X11 and driven through `POST /start` → speak/record → `POST /stop` → `GET /last-transcription`
- **THEN** the status SHALL transition through recording to idle and the last transcription SHALL be non-empty and well-formed

#### Scenario: missing prerequisite surfaces as UNVERIFIED on Linux
- **WHEN** the microphone, model, `xdotool`, or X11 session is unavailable during the driven cycle
- **THEN** the result SHALL be reported as UNVERIFIED, not as a pass

_Tier: live-driven — real daemon driven over HTTP against real mic + model; unattended; runs under `-m linux`._

### Requirement: Absent seams report UNVERIFIED to the validation run
When smoke-tier checks run under the release-validation flow, an absent device, permission, or binary SHALL be surfaced as UNVERIFIED to the run summary rather than as a silent pass. A pytest-level `skip` SHALL be classified as UNVERIFIED by the orchestrator so that a green summary cannot conceal an unexercised seam.

#### Scenario: a skipped smoke check is classified UNVERIFIED
- **WHEN** a smoke-tier check skips because its device/permission/binary is absent
- **THEN** the validation run SHALL classify it as UNVERIFIED and include it in the distinct UNVERIFIED count

_Tier: unit-pure — the skip→UNVERIFIED classification is a pure mapping over check results._

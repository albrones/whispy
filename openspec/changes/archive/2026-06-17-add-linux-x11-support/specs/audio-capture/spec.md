## MODIFIED Requirements

### Requirement: Recording readiness wait
The audio engine SHALL capture audio via the cross-platform `sounddevice` (PortAudio) backend rather than a `sox` subprocess, writing the same 16 kHz mono WAV at the established recording path so transcription is unaffected. The engine SHALL wait for the capture stream to begin delivering audio before returning from start, so that the audio device's cold-start delay does not produce an empty first recording. The wait SHALL terminate when capture has started, when the stream fails to open, or when a readiness timeout elapses — and SHALL never block indefinitely.

#### Scenario: Recording becomes ready
- **WHEN** the `sounddevice` capture stream starts and begins delivering audio frames
- **THEN** the start call SHALL return with recording active

_Tier: platform-real — needs a real audio device; deferred to the per-OS smoke tier._

#### Scenario: Readiness times out
- **WHEN** capture never begins delivering audio within the readiness timeout
- **THEN** the start call SHALL return anyway and SHALL log a warning that the first recording may be empty

_Tier: platform-real — deferred to the per-OS smoke tier._

#### Scenario: Capture stream fails to open
- **WHEN** the `sounddevice` stream cannot be opened (no device / busy)
- **THEN** the readiness wait SHALL stop and SHALL log a warning rather than block

_Tier: platform-real — deferred to the per-OS smoke tier._

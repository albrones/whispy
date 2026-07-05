# audio-capture Delta — Refresh Audio Devices Before Capture

## ADDED Requirements

### Requirement: Follow system default input device
The audio engine SHALL re-enumerate the audio backend's device list before opening each capture stream, so that capture targets the system default input device current at the moment recording starts — including after a Bluetooth device connects or disconnects, or the machine wakes from sleep. When the device-list refresh itself fails, the engine SHALL proceed to open the stream anyway (degrading to prior behavior) rather than abort the recording.

#### Scenario: Default input changed since daemon start
- **WHEN** the system default input device has changed since the audio backend was initialized (e.g. a Bluetooth headset disconnected) and a recording starts
- **THEN** the engine SHALL refresh the device list before opening the stream, and the stream SHALL capture from the current system default input device

_Tier: unit-mocked — refresh call pinned and ordered before stream open._

#### Scenario: Device refresh fails
- **WHEN** the device-list refresh raises an error
- **THEN** the engine SHALL log the error and still attempt to open the capture stream

_Tier: unit-mocked._

### Requirement: Retry stream open after refresh
When opening the capture stream fails, the audio engine SHALL refresh the device list once more and retry the open exactly once. Only after the retry also fails SHALL the engine give up on capturing for this recording.

#### Scenario: First open fails, retry succeeds
- **WHEN** the first stream-open attempt raises and the retry after a second refresh succeeds
- **THEN** recording SHALL proceed normally with the retried stream and no capture failure SHALL be reported

_Tier: unit-mocked._

#### Scenario: Retry also fails
- **WHEN** both the initial open and the single retry raise
- **THEN** the engine SHALL stop retrying, record the capture failure for reporting, and the readiness wait SHALL stop rather than block

_Tier: unit-mocked._

### Requirement: Capture failure reported to user
When the capture stream cannot be opened (after the retry), the failure SHALL be surfaced to the user through the engine's callback mechanism — mirroring the existing model-load-failure pattern — so the UI can post a notification, instead of the recording silently capturing nothing.

#### Scenario: Stream open fails after retry
- **WHEN** the capture stream fails to open after the refresh-and-retry sequence and a recording start was requested
- **THEN** the engine SHALL fire the capture-failed callbacks with a human-readable message identifying that no audio is being captured

_Tier: unit-mocked — `engine.py` fan-out mirrors `on_model_load_failed`._

#### Scenario: Stream opens normally
- **WHEN** the capture stream opens successfully
- **THEN** no capture-failed callback SHALL fire

_Tier: unit-mocked._

## MODIFIED Requirements

### Requirement: Recording readiness wait
The audio engine SHALL capture audio via the cross-platform `sounddevice` (PortAudio) backend rather than a `sox` subprocess, writing the same 16 kHz mono WAV at the established recording path so transcription is unaffected. The engine SHALL wait for the capture stream to begin delivering audio before returning from start, so that the audio device's cold-start delay does not produce an empty first recording. The wait SHALL terminate when capture has started, when the stream fails to open (after the single refresh-and-retry attempt), or when a readiness timeout elapses — and SHALL never block indefinitely.

#### Scenario: Recording becomes ready
- **WHEN** the `sounddevice` capture stream starts and begins delivering audio frames
- **THEN** the start call SHALL return with recording active

_Tier: platform-real — needs a real audio device; deferred to the per-OS smoke tier._

#### Scenario: Readiness times out
- **WHEN** capture never begins delivering audio within the readiness timeout
- **THEN** the start call SHALL return anyway and SHALL log a warning that the first recording may be empty

_Tier: platform-real — deferred to the per-OS smoke tier._

#### Scenario: Capture stream fails to open
- **WHEN** the `sounddevice` stream cannot be opened (no device / busy) even after the refresh-and-retry sequence
- **THEN** the readiness wait SHALL stop, the engine SHALL log a warning rather than block, and the capture failure SHALL be reported for user notification

_Tier: unit-mocked — was platform-real; the refresh/retry/notify path is mockable._

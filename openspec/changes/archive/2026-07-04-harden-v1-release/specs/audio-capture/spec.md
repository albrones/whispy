## ADDED Requirements

### Requirement: Recording files are created owner-only
Every recording WAV (the main recording and each streaming chunk) SHALL be created with `0o600` permissions (owner read/write only), regardless of the process umask, so recorded voice audio is never world-readable in a shared temporary directory.

#### Scenario: Recording WAV is owner-only under a permissive umask
- **WHEN** a recording starts under a permissive process umask (e.g. `0o022`)
- **THEN** the resulting recording WAV SHALL have file mode `0o600`

_Tier: unit-pure — `test_audio.py::TestRecordingFilePermissions` (POSIX only)._

#### Scenario: Streaming chunk WAV is owner-only
- **WHEN** a streaming chunk WAV is emitted under a permissive process umask
- **THEN** the resulting chunk WAV SHALL have file mode `0o600`

_Tier: unit-pure — `test_audio.py::TestRecordingFilePermissions` (POSIX only)._

### Requirement: Stale recording files are swept at startup
`AudioEngine` initialization SHALL best-effort remove leftover `whispy-*.wav` files (from a prior crash or an incomplete cleanup) from the temporary directory, and a failure during the sweep SHALL NOT prevent `AudioEngine` from starting.

#### Scenario: Startup removes a leftover recording
- **WHEN** a stale `whispy-<uuid>.wav` file exists in the temp directory when `AudioEngine` is constructed
- **THEN** the file SHALL be removed as part of construction

_Tier: unit-pure — `test_audio.py::TestStaleRecordingSweep`._

#### Scenario: Sweep failure does not break startup
- **WHEN** listing or removing stale recordings raises an OS-level error
- **THEN** `AudioEngine` construction SHALL still succeed

_Tier: unit-mocked — `test_audio.py::TestStaleRecordingSweep::test_sweep_failure_does_not_break_startup`._

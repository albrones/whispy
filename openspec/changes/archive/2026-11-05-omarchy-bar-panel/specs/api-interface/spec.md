## ADDED Requirements

### Requirement: Live input level
`GET /level` SHALL return `{"level": <number>, "is_recording": <bool>}`, behind the same authentication gate as every endpoint. `level` SHALL be the capture stream's input level clamped to 0..1 while recording, and 0 otherwise. A successful `/level` request SHALL NOT be written to the request log; a refused one SHALL.

#### Scenario: Level while recording
- **WHEN** an authenticated client calls `GET /level` while recording
- **THEN** the API SHALL return `200` with the engine's level clamped to 0..1 and `is_recording: true`

_Tier: unit-mocked — `tests/test_api/test_server.py::TestGetLevel`._

#### Scenario: Level at rest
- **WHEN** nothing is being recorded
- **THEN** `level` SHALL be 0 and `is_recording` false

_Tier: unit-mocked — `tests/test_api/test_server.py::TestGetLevel`._

#### Scenario: Polls stay out of the log
- **WHEN** `/level` answers `200`
- **THEN** no request line SHALL be printed for it, while other requests still are

_Tier: unit-mocked — `tests/test_api/test_server.py::TestGetLevel`._

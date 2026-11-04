## ADDED Requirements

### Requirement: Transcribe an uploaded WAV
`POST /transcribe` SHALL accept a raw `audio/wav` body (16 kHz, mono, 16-bit PCM), behind the same authentication gate as every endpoint, transcribe it with the current config and return `{"text": "…"}`. It SHALL NOT inject keystrokes and SHALL NOT keep the audio on disk. The body size SHALL be capped before it is read. Errors SHALL be JSON objects with an `error` field naming what was expected: `400` for a missing body, a non-WAV body, a wrong `Content-Type` or an unsupported format; `413` for an oversized body; `503` while the model is not loaded.

#### Scenario: A WAV is transcribed
- **WHEN** an authenticated client posts a 16 kHz mono 16-bit WAV with `Content-Type: audio/wav`
- **THEN** the API SHALL return `200` with `{"text": …}` and no keystroke SHALL be injected

_Tier: unit-mocked — `tests/test_api/test_server.py`._

#### Scenario: A non-WAV body is rejected
- **WHEN** the body is not a RIFF/WAVE file, or the `Content-Type` is not `audio/wav`
- **THEN** the API SHALL return `400` with an `error` naming the expected format

_Tier: unit-mocked — `tests/test_api/test_server.py`._

#### Scenario: An oversized body is rejected before it is read
- **WHEN** the `Content-Length` exceeds the audio cap
- **THEN** the API SHALL return `413` without reading the body

_Tier: unit-mocked — `tests/test_api/test_server.py`._

#### Scenario: The temporary audio file is removed
- **WHEN** a transcription completes or fails
- **THEN** no copy of the uploaded audio SHALL remain on disk

_Tier: unit-mocked — `tests/test_api/test_server.py`._

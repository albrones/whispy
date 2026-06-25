# api-interface Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements
### Requirement: HTTP API Interface
The API interface SHALL provide a set of RESTful endpoints to allow external control and status monitoring of the daemon. The asynchronous stop endpoint (`/stop-async`) SHALL signal the transcription worker via the engine's public stop event so that transcription proceeds in the background, and SHALL return a success response rather than an error.

#### Scenario: Status Check
- **WHEN** a GET request is made to `/status`
- **THEN** the API SHALL return a JSON object containing current recording, transcription, and listener status

_Tier: unit-mocked — `test_api/test_server.py` (real HTTP server, engine with mocked audio/Whisper)._

#### Scenario: Manual Start/Stop
- **WHEN** a POST request is made to `/start` or `/stop`
- **THEN** the API SHALL trigger the corresponding command in the core engine and return a status response

_Tier: unit-mocked — `test_api/test_server.py`._

#### Scenario: Async stop signals the worker
- **WHEN** a POST request is made to `/stop-async`
- **THEN** the API SHALL stop recording, set the engine's stop event so the transcription worker wakes, and return a 200 response with `{"status": "stopping"}` (without raising)

_Tier: unit-mocked — `test_api/test_server.py`._

### Requirement: Configuration Management via API
The API SHALL allow for remote configuration updates (e.g., changing model size or language) through specific endpoints.

#### Scenario: Remote Config Update
- **WHEN** a POST request with new configuration parameters is sent to `/config`
- **THEN** the API SHALL update the local configuration and trigger any necessary engine reloads (e.g., model reloading)

_Tier: unit-mocked — `test_api/test_server.py`._

### Requirement: Authenticated loopback control API
The HTTP API SHALL require a per-install secret token on every request and SHALL reject browser-originated and DNS-rebinding requests, so that no web page running in the user's browser can control the daemon or read its data.

#### Scenario: Missing or wrong token is rejected
- **WHEN** a request is made to any endpoint without the valid per-install token
- **THEN** the API SHALL respond `401` and perform no side effect (no recording start/stop, no config change, no transcription)

#### Scenario: Valid token is accepted
- **WHEN** a request carries the valid per-install token
- **THEN** the API SHALL process it normally

#### Scenario: Foreign Host header is rejected
- **WHEN** a request arrives whose `Host` header is not exactly `127.0.0.1:<port>` or `localhost:<port>`
- **THEN** the API SHALL respond `403` (DNS-rebinding defense)

#### Scenario: Browser-originated request is rejected
- **WHEN** a request carries an `Origin` or `Referer` header
- **THEN** the API SHALL respond `403`

#### Scenario: Oversized body is rejected
- **WHEN** a request declares a `Content-Length` greater than the configured cap (64 KB)
- **THEN** the API SHALL respond `413` without reading the request body

### Requirement: Transcription-file path is restricted
The `POST /transcribe-file` endpoint SHALL only transcribe files inside an allow-listed directory, so it cannot be used to probe or read arbitrary filesystem paths.

#### Scenario: Path outside the allow-list is rejected
- **WHEN** a request to `/transcribe-file` supplies a path that resolves outside the allow-listed fixtures directory
- **THEN** the API SHALL respond `403` and SHALL NOT open or transcribe the file


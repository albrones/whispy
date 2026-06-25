## ADDED Requirements

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

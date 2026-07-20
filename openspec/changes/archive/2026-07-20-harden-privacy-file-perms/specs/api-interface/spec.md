## MODIFIED Requirements

### Requirement: Authenticated loopback control API
The HTTP API SHALL require a per-install secret token on every request and SHALL reject browser-originated and DNS-rebinding requests, so that no web page running in the user's browser can control the daemon or read its data. The API SHALL fail closed: if the server has no configured token (`auth_token` is `None` or an empty string), every request SHALL be rejected with `401` rather than falling through to the Host/Origin checks alone.

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

#### Scenario: No configured token fails closed
- **WHEN** the server is started with `auth_token` set to `None` or an empty string
- **THEN** every request to every endpoint SHALL be rejected with `401`, even one that satisfies the Host and Origin checks

_Tier: unit-mocked — `test_api/test_server.py` (server started with `auth_token=None`, all endpoints asserted to return `401`)._

## ADDED Requirements

### Requirement: HTTP API Interface
The API interface SHALL provide a set of RESTful endpoints to allow external control and status monitoring of the daemon.

#### Scenario: Status Check
- **WHEN** a GET request is made to `/status`
- **THEN** the API SHALL return a JSON object containing current recording, transcription, and listener status

#### Scenario: Manual Start/Stop
- **WHEN** a POST request is made to `/start` or `/stop`
- **THEN** the API SHALL trigger the corresponding command in the core engine and return a status response

### Requirement: Configuration Management via API
The API SHALL allow for remote configuration updates (e.g., changing model size or language) through specific endpoints.

#### Scenario: Remote Config Update
- **WHEN** a POST request with new configuration parameters is sent to `/config`
- **THEN** the API SHALL update the local configuration and trigger any necessary engine reloads (e.g., model reloading)

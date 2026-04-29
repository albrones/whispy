## MODIFIED Requirements

### Requirement: Configuration Management via API
The API SHALL allow for remote configuration updates (e.g., changing model size or language) through specific endpoints. The API SHALL reject `trigger_key` and `compute_key` configuration updates with a 400 error, as these options are no longer configurable.

#### Scenario: Remote Config Update
- **WHEN** a POST request with new configuration parameters is sent to `/config`
- **THEN** the API SHALL update the local configuration and trigger any necessary engine reloads (e.g., model reloading)

#### Scenario: Reject trigger_key config update
- **WHEN** a POST request includes `trigger_key` in the config
- **THEN** the API SHALL return a 400 error with a message explaining that trigger_key is no longer configurable

#### Scenario: Reject compute_key config update
- **WHEN** a POST request includes `compute_key` in the config
- **THEN** the API SHALL return a 400 error with a message explaining that compute_key is no longer configurable

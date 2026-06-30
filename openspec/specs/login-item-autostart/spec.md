# login-item-autostart Specification

## Purpose
TBD - created by archiving change add-login-item-toggle. Update Purpose after archive.
## Requirements
### Requirement: Start-at-login setting in the Settings menu

The macOS menu bar menu SHALL present a "Start at login" toggle within its **Settings** section, using the same checked-title styling as the other settings toggles (e.g. "Copy to clipboard"). Enabling it SHALL register the running app bundle as a macOS login item; disabling it SHALL unregister it.

#### Scenario: Enabling start-at-login

- **WHEN** the user clicks the "Start at login" toggle while it is off
- **THEN** Whispy registers the running `Whispy.app` bundle as a login item
- **AND** the menu item shows its checked/enabled state

#### Scenario: Disabling start-at-login

- **WHEN** the user clicks the "Start at login" toggle while it is on
- **THEN** Whispy unregisters the app bundle as a login item
- **AND** the menu item shows its unchecked/disabled state

### Requirement: Persisted setting

The start-at-login choice SHALL be persisted in Whispy configuration as a boolean `start_at_login`, validated and defaulted (default `false`) like the other settings. The toggle's checked state SHALL reflect this persisted value, and toggling SHALL write the new value to config.

#### Scenario: Choice persists across restarts

- **WHEN** the user enables "Start at login" and Whispy is later restarted
- **THEN** the persisted config has `start_at_login = true`
- **AND** the toggle shows as on

#### Scenario: Invalid persisted value is defaulted

- **WHEN** the config file contains a non-boolean `start_at_login`
- **THEN** Whispy falls back to the default (`false`) without crashing

### Requirement: Startup reconciliation of OS state to config

On startup, when the setting is available (bundle + macOS 13+), Whispy SHALL reconcile the OS login-item registration to the persisted `start_at_login` value: register if the saved intent is on but the OS is not enabled, and unregister if the saved intent is off but the OS is still enabled.

#### Scenario: Re-register after the bundle moved or was rebuilt

- **WHEN** `start_at_login` is `true` in config but the OS reports the login item is not enabled at startup
- **THEN** Whispy re-registers the running bundle as a login item

#### Scenario: Honor a saved opt-out

- **WHEN** `start_at_login` is `false` in config but the OS still reports the login item enabled at startup
- **THEN** Whispy unregisters the login item

### Requirement: Availability gating

The "Start at login" toggle SHALL be shown only when Whispy is running as a `.app` bundle and on a macOS version where `SMAppService` is available (macOS 13+). When unavailable, the toggle SHALL be hidden, and no error SHALL be raised on menu construction.

#### Scenario: Running as loose script

- **WHEN** Whispy runs from the loose-script / `install.sh` path (no resolvable app bundle)
- **THEN** the "Start at login" toggle is not shown in the menu

#### Scenario: SMAppService unavailable

- **WHEN** Whispy runs on a macOS version older than 13 (or `ServiceManagement` cannot be loaded)
- **THEN** the "Start at login" toggle is not shown
- **AND** the rest of the menu builds normally

### Requirement: No new dependency

The login-item integration SHALL reach `SMAppService` via dynamic framework loading on the already-installed `pyobjc-core` (e.g. `objc.loadBundle`), without adding a new Python package dependency.

#### Scenario: Dependency set unchanged

- **WHEN** the feature is implemented
- **THEN** no new entry is added to the project's runtime dependencies for this feature


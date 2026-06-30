# macos-install Specification

## Purpose
TBD - created by archiving change consolidate-macos-install. Update Purpose after archive.
## Requirements
### Requirement: Single OS-detecting install entrypoint

The `curl | bash` entrypoint (`scripts/bootstrap.sh`) SHALL detect the operating system and route to the correct install flow, so that one documented command works on both macOS and Linux. On Linux it SHALL run the existing venv + `systemd --user` flow unchanged; on macOS it SHALL drive the `Whispy.app` build-and-install flow.

#### Scenario: Linux routes to the systemd flow

- **WHEN** the entrypoint runs on Linux (`uname` = `Linux`)
- **THEN** it SHALL create the venv and install/enable the `systemd --user` unit, exactly as before this change

#### Scenario: macOS routes to the .app flow

- **WHEN** the entrypoint runs on macOS (`uname` = `Darwin`)
- **THEN** it SHALL build `Whispy.app`, install it to `/Applications`, and open it — and SHALL NOT install a `com.whispy` LaunchAgent

### Requirement: Signed .app is the sole recommended macOS install

The signed `Whispy.app` bundle SHALL be the single recommended and supported macOS install path. User-facing documentation SHALL present exactly one recommended macOS path (the `.app`), not two.

#### Scenario: Documentation presents one recommended macOS path

- **WHEN** a user reads the README install section
- **THEN** the `.app` bundle SHALL be the only path marked recommended for macOS
- **AND** no separate LaunchAgent-based "recommended" macOS install is offered

### Requirement: macOS build is local, with a guarded toolchain fallback

On macOS the entrypoint SHALL build `Whispy.app` locally (so the bundle is not Gatekeeper-quarantined), rather than downloading a prebuilt bundle. When the build toolchain (Xcode Command Line Tools) is unavailable, it SHALL degrade to printing the manual build commands and an actionable hint instead of failing opaquely.

#### Scenario: Toolchain present builds automatically

- **WHEN** the macOS entrypoint runs and Xcode Command Line Tools are present
- **THEN** it SHALL build and install `Whispy.app` without further user steps

#### Scenario: Toolchain absent degrades gracefully

- **WHEN** the macOS entrypoint runs and Xcode Command Line Tools are absent
- **THEN** it SHALL print the manual `.app` build commands and an `xcode-select --install` hint
- **AND** it SHALL exit without a fatal/opaque error

### Requirement: install.sh provisions only the venv on macOS

On macOS, `install.sh` SHALL provision only the build prerequisites (Python venv, dependencies, icons, optional `WHISPER_MODEL` → config) and SHALL NOT write or load a `com.whispy` LaunchAgent. The Linux branch (systemd `--user` unit) is unaffected.

#### Scenario: macOS install creates no LaunchAgent

- **WHEN** `install.sh` runs on macOS
- **THEN** it SHALL create the venv and dependencies
- **AND** no `~/Library/LaunchAgents/com.whispy.plist` SHALL be created or loaded

### Requirement: Login item is the only macOS autostart

macOS start-at-login SHALL be provided solely by the in-app login-item toggle (`SMAppService`, per the `login-item-autostart` capability). No LaunchAgent-based autostart SHALL be installed on macOS.

#### Scenario: Autostart is the in-app toggle

- **WHEN** a macOS user wants Whispy to start at login
- **THEN** the only mechanism SHALL be the in-app "Start at login" toggle
- **AND** no `com.whispy` LaunchAgent SHALL be involved

### Requirement: Migrate upgraders off a stale LaunchAgent

The macOS install and uninstall paths SHALL remove any pre-existing legacy LaunchAgent — both the older `com.whisper-dictation` (pre-rebrand "Whisper Dictation") and the intermediate `com.whispy` — by unloading/booting out and deleting each plist, so that an upgraded install does not run two daemons competing for `:9090`.

#### Scenario: Existing LaunchAgent is removed on upgrade

- **WHEN** the macOS entrypoint runs and either `~/Library/LaunchAgents/com.whisper-dictation.plist` or `~/Library/LaunchAgents/com.whispy.plist` exists
- **THEN** it SHALL unload and delete each such LaunchAgent before launching `Whispy.app`
- **AND** only one daemon SHALL serve `:9090`

#### Scenario: Uninstall removes the LaunchAgent and login item

- **WHEN** the user runs the macOS uninstall
- **THEN** any `com.whisper-dictation` and `com.whispy` LaunchAgent SHALL be removed
- **AND** the login-item registration SHALL be unregistered


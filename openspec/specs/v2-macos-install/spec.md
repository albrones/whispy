# v2-macos-install Specification

## Purpose
Lets Whispy V2 run on macOS as an installed, signed menu bar app: permissions
that survive rebuilds, an install next to V1, a one-command rebuild, and an
optional start at login.

## Requirements

### Requirement: V2 installs as its own signed app bundle
The build SHALL produce `Whispy V2.app` with bundle identifier `com.whispy.v2`, marked as an agent app (menu bar icon, no Dock icon), declaring why it needs the microphone, and holding every library the binary loads. It SHALL be signed with the "Whispy Local Signing" identity, or ad hoc with a warning when that identity is absent. It SHALL install to `/Applications/Whispy V2.app` and SHALL NOT modify `/Applications/Whispy.app`.

#### Scenario: The bundle is signed with the stable identity
- **WHEN** the bundle is built on a Mac that holds the "Whispy Local Signing" identity
- **THEN** `codesign --verify --strict` SHALL pass and the signature SHALL NOT be ad hoc

_Tier: script — `make v2-app` then `codesign -dvv`._

#### Scenario: V1 is left in place
- **WHEN** V2 is installed on a Mac where `/Applications/Whispy.app` exists
- **THEN** V1's bundle SHALL be byte-for-byte unchanged and both apps SHALL be listed in `/Applications`

_Tier: script — checksum of V1's executable before and after `make v2-reinstall`._

#### Scenario: The bundle runs without the build tree
- **WHEN** the installed bundle is launched after `v2/target` has been deleted
- **THEN** it SHALL start and load its models

_Tier: manual._

### Requirement: Permissions survive a rebuild
Microphone, Input Monitoring and Accessibility SHALL be granted to the V2 bundle, not to a terminal. Once granted, they SHALL hold across rebuilds and reinstalls signed with the same identity.

#### Scenario: A reinstall keeps Input Monitoring
- **WHEN** Input Monitoring was granted to Whispy V2 and the app is rebuilt and reinstalled
- **THEN** the Fn key SHALL work after relaunch without a new prompt

_Tier: `[à l'usage]`._

### Requirement: One command rebuilds, reinstalls and relaunches V2
`make v2-reinstall` SHALL build V2 in release mode, assemble and sign the bundle, quit the running V2 if any, replace the installed copy, launch it, and wait until its control socket answers `status`. It SHALL fail with a non-zero exit when the socket does not answer within 30 s.

#### Scenario: A source change reaches the installed app
- **WHEN** a change in `v2/whispy2` is followed by `make v2-reinstall`
- **THEN** the installed bundle's executable SHALL be the one just built and the socket SHALL answer `status`

_Tier: script._

#### Scenario: A V2 that does not come up fails the command
- **WHEN** the relaunched V2 does not answer on its socket within 30 s
- **THEN** `make v2-reinstall` SHALL exit non-zero and print the last lines of the V2 log

_Tier: script._

### Requirement: Start at login is a menu toggle backed by the OS
The menu SHALL offer "Start at login" with a check mark reflecting the OS login-item state for the V2 bundle. Choosing it SHALL register or unregister the bundle as a login item. The OS state SHALL be the only record of this setting. When registration needs the user's approval in System Settings, the menu SHALL say so.

#### Scenario: Turning it on
- **WHEN** the user chooses "Start at login" while it is unchecked
- **THEN** the bundle SHALL be registered as a login item and the item SHALL show a check mark

_Tier: manual — check System Settings → General → Login Items._

#### Scenario: Running outside a bundle
- **WHEN** the binary runs from `v2/target` instead of an installed bundle
- **THEN** "Start at login" SHALL be shown disabled with a note that it needs the installed app

_Tier: unit — the menu model with no bundle path._

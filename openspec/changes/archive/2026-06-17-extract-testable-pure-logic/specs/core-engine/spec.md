## MODIFIED Requirements

### Requirement: Restart uses correct entry point
The menu bar "Restart" item SHALL launch the application using the correct entry point file `whispy_daemon.py` located at the project root. The resolution of that path and the check for its existence SHALL be performed by a pure, unit-tested helper independent of the menu bar UI; the menu callback SHALL delegate path resolution to that helper and only then perform the relaunch and quit.

#### Scenario: Restart path resolves to daemon
- **WHEN** the path-resolution helper is invoked
- **THEN** it SHALL return the path to `whispy_daemon.py` at the project root

_Tier: unit-pure — covered by the extracted helper test._

#### Scenario: Restart path works from any working directory
- **WHEN** the path-resolution helper is invoked from any current working directory
- **THEN** it SHALL return the same project-root `whispy_daemon.py` path (resolution is independent of cwd)

_Tier: unit-pure — covered by the extracted helper test._

#### Scenario: Missing daemon script is detected before relaunch
- **WHEN** the existence check reports that the resolved script does not exist
- **THEN** the restart action SHALL NOT spawn a process and SHALL surface a "Restart file not found" condition

_Tier: unit-pure (existence check) — the alert/relaunch UI stays manual-ui._

#### Scenario: Restart exits current instance
- **WHEN** the user clicks the "Restart" menu item and the script exists
- **THEN** the application launches the new instance and the current menu bar instance quits

_Tier: manual-ui — relaunch + quit is not unit-testable._

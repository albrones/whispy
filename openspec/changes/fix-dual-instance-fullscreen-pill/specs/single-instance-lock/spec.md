## ADDED Requirements

### Requirement: Exclusive single-instance daemon

At most one Whispy daemon SHALL run at a time on a host. The daemon SHALL acquire an exclusive lock by binding the control port `127.0.0.1:9090`. If the port is already held, the daemon SHALL NOT fall back to another port; it SHALL log a clear message that another instance is already running and exit non-zero.

#### Scenario: First instance acquires the lock

- **WHEN** no Whispy daemon is running and the daemon starts
- **THEN** it binds `127.0.0.1:9090` and continues startup

#### Scenario: Second instance fails fast

- **WHEN** a Whispy daemon is already bound to `127.0.0.1:9090` and a second instance starts
- **THEN** the second instance logs that another instance is already running and exits without binding any other port and without starting an event tap, audio capture, or model load

#### Scenario: No port drift

- **WHEN** `127.0.0.1:9090` is unavailable
- **THEN** the daemon does NOT attempt to bind `9091` or any other port

### Requirement: Restart hands off the lock without overlap

The in-app Restart action SHALL ensure the previous instance releases `127.0.0.1:9090` before the replacement instance attempts to bind it, so the replacement is guaranteed to be the only running daemon.

#### Scenario: Restart leaves exactly one instance

- **WHEN** the user triggers Restart from the menu
- **THEN** the replacement daemon binds `127.0.0.1:9090` successfully and exactly one Whispy daemon is running once the restart completes

#### Scenario: Replacement does not race the old instance

- **WHEN** Restart relaunches the app
- **THEN** the relaunch is sequenced so the old instance has released the lock before the new instance binds it (the new instance never silently drifts to a fallback port)

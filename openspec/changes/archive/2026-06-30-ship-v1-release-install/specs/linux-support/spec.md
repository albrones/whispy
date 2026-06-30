## ADDED Requirements

### Requirement: Advertised Linux install path is honest
The documented Linux install path SHALL actually install and start the daemon, OR the documentation SHALL NOT advertise an install path that does not function on Linux.

#### Scenario: User follows the Linux install instructions
- **WHEN** a Linux user runs the install path the docs advertise for Linux
- **THEN** either the daemon SHALL be installed and started (e.g. via a `systemd --user` unit), OR the docs SHALL clearly scope that path to macOS and present the supported Linux procedure — never silently no-op

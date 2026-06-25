## ADDED Requirements

### Requirement: Linux hotkey listener warns on Wayland and does not latch
The Linux hotkey listener SHALL warn the user when started under a Wayland session, and SHALL reset its held-key state on start so a previously missed release does not permanently swallow the next press.

#### Scenario: Started under Wayland
- **WHEN** the Linux hotkey listener `start()` runs in a Wayland session
- **THEN** it SHALL emit the Wayland guidance message (not only on a later exception)

#### Scenario: Restart after a missed release
- **WHEN** the listener is (re)started while its internal held flag was left set
- **THEN** `start()` SHALL reset the held flag so the next press is detected

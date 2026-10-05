## MODIFIED Requirements

### Requirement: Daemon log file rotates instead of growing unbounded
`whispy_daemon.py` SHALL configure `~/.whispy.log` with size-based rotation (1 MB per file, 3 backups retained) rather than a single unbounded log file.

Diagnostics written to standard error SHALL also be captured to a file,
`~/.whispy-error.log`, under the same rotation bounds. Whispy ships as a GUI
`.app` with no attached terminal, so a handler that writes only to the process
stream discards every stderr diagnostic — including the trigger-listener's
recovery and failure messages, which are the primary evidence for diagnosing a
dead hotkey. A diagnostic that is emitted but unreadable is equivalent to one
that was never emitted, and this file is already named in the user-facing
documentation as the place to look.

Standard output has no such capture and SHALL NOT be used for diagnostics: the
bundled `.app` discards it entirely. The line confirming that the trigger
listener came up — the first thing to check when the hotkey is dead — SHALL be
emitted through the logger so it lands in `~/.whispy.log` alongside the
`[fsm]` and `[audio]` lines it has to be read against.

#### Scenario: Log file reaches the size limit
- **WHEN** `~/.whispy.log` reaches the configured 1 MB size limit
- **THEN** it SHALL be rotated to a backup and a fresh log file SHALL be started, up to 3 retained backups

_Tier: unit-mocked — `test_config_validation.py` / daemon logging config._

#### Scenario: A stderr diagnostic is readable after the daemon writes it
- **WHEN** the daemon writes a diagnostic to standard error while running as a GUI `.app`
- **THEN** that diagnostic SHALL appear in `~/.whispy-error.log`

_Tier: unit-mocked — daemon logging configuration asserted directly._

#### Scenario: The trigger listener records that it came up
- **WHEN** the trigger listener starts successfully
- **THEN** a line naming the active trigger SHALL appear in `~/.whispy.log`, not on standard output

_Tier: unit-mocked — `test_event_tap_e2e.py`._

#### Scenario: The error log is bounded
- **WHEN** `~/.whispy-error.log` reaches its configured size limit
- **THEN** it SHALL be rotated to a backup with a bounded number of retained backups, and SHALL NOT grow without limit

_Tier: unit-mocked — daemon logging configuration asserted directly._

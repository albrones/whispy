## ADDED Requirements

### Requirement: Clipboard injection snapshots and restores the clipboard
Clipboard-mode injection SHALL capture the clipboard's contents before overwriting it with the transcript, and SHALL restore that captured content after the paste keystroke completes, so dictation does not permanently destroy whatever the user had previously copied. When the paste step itself fails, the restore SHALL NOT run, leaving the transcript on the clipboard as the manual-paste fallback.

#### Scenario: Clipboard is restored after a successful paste
- **WHEN** clipboard-mode injection copies the transcript, pastes it via `Cmd+V`, and the paste succeeds
- **THEN** the engine SHALL restore the clipboard to the content it held immediately before the transcript was copied

#### Scenario: Failed paste leaves the transcript on the clipboard
- **WHEN** the paste keystroke step fails (e.g. a `1002` permission denial)
- **THEN** the restore step SHALL NOT run, and the transcript SHALL remain on the clipboard as the fallback the user can paste manually

#### Scenario: Snapshot failure does not block injection
- **WHEN** capturing the pre-dictation clipboard content fails (e.g. the snapshot command is unavailable or errors)
- **THEN** injection SHALL proceed with the copy and paste steps regardless, and the restore step SHALL fall back to an empty clipboard rather than raise

_Tier: unit-mocked — `test_injection.py::TestClipboardRestore` (`subprocess.run`/`Popen` mocked)._

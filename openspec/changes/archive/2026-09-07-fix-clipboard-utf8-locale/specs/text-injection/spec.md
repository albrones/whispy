## ADDED Requirements

### Requirement: Clipboard hand-off preserves non-ASCII text

Clipboard-mode injection, copy-only delivery, and the pre-dictation clipboard
snapshot/restore SHALL deliver and restore text byte-exact as UTF-8, regardless
of the locale environment the daemon was launched with. In particular, when the
app is launched by launchd or Finder with no `LANG` or `LC_*` variables, accented
characters SHALL NOT be re-encoded through the platform's legacy default
encoding.

#### Scenario: Accented dictation survives clipboard mode without a locale

- **WHEN** `copy_to_clipboard` is enabled, the process environment carries no `LANG`/`LC_*` variable, and the transcript « là créer ça » is injected
- **THEN** the pasted text SHALL be exactly « là créer ça »

#### Scenario: Previous clipboard with accents is restored intact

- **WHEN** the clipboard holds « déjà vu » before dictation and clipboard-mode injection completes successfully
- **THEN** the clipboard SHALL be restored to exactly « déjà vu »

#### Scenario: Copy-only delivery preserves accents

- **WHEN** the engine hands a transcript back through the copy-only path (recording-limit stop)
- **THEN** the clipboard SHALL contain the transcript byte-exact as UTF-8

#### Scenario: Every clipboard helper receives the same locale

- **WHEN** any clipboard helper process (copy, paste-trigger, restore, snapshot) is spawned by the macOS injector
- **THEN** it SHALL run with a UTF-8 locale forced in its environment, so snapshot and restore agree on the encoding

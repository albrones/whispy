# text-injection Specification

## Purpose
Injecting transcribed text into the focused application behind a per-OS
`TextInjector` port: `osascript` on macOS, `xdotool` on Linux/X11, with an
identical clipboard-paste vs keystroke contract.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

NOTE: pure injection behaviors tested today but not yet specced — quote escaping,
empty-text no-op, clipboard/keystroke mode switch (`test_injection.py`,
`unit-pure`). Add as requirements in a follow-up (candidate for step C).
## Requirements
### Requirement: Text Injection via System Services
The injection engine SHALL provide a mechanism to input transcribed text into the active application using system-level automation, **behind a `TextInjector` port with a per-OS adapter**: `osascript` on macOS and `xdotool` on Linux/X11. The injected result and the clipboard-vs-keystroke configuration contract SHALL be identical across adapters.

#### Scenario: Successful Text Injection
- **WHEN** a transcription is completed and text injection is enabled
- **THEN** the active platform's injector adapter SHALL inject the transcribed text into the currently focused application field

_Tier: platform-real — `subprocess` mocked on macOS; the real seam (osascript / xdotool) is not exercised in CI. Deferred to the per-OS smoke tier._

#### Scenario: Adapter selected by platform
- **WHEN** the engine injects text
- **THEN** it SHALL use the `osascript` adapter on macOS and the `xdotool` adapter on Linux, selected via the platform factory rather than a direct import

_Tier: unit-mocked — `sys.platform`/factory patched._

### Requirement: Clipboard Integration
The injection engine SHALL support an option to copy the transcribed text to the system clipboard instead of (or in addition to) direct keystroke injection.

#### Scenario: Clipboard Copy
- **WHEN** the "copy to clipboard" setting is enabled and a transcription completes
- **THEN** the engine SHALL update the system clipboard with the transcribed text

_Tier: macos-real — clipboard write goes through mocked `osascript` in CI. Real-seam coverage deferred to step A._

### Requirement: Pure injection input handling
The injection engine SHALL apply deterministic, unit-tested input handling before any system call: it SHALL escape double quotes in the text destined for `osascript`, SHALL do nothing when the text is empty, and SHALL select the clipboard path versus the keystroke path based on the `copy_to_clipboard` setting. These behaviors SHALL be verifiable without invoking `osascript`.

#### Scenario: Double quotes are escaped
- **WHEN** the text to inject contains double-quote characters
- **THEN** the engine SHALL escape them before constructing the `osascript` command

_Tier: unit-pure — `test_injection.py::TestQuoteEscaping`._

#### Scenario: Empty text is a no-op
- **WHEN** the text to inject is empty
- **THEN** the engine SHALL perform no injection and SHALL NOT spawn a process

_Tier: unit-pure — `test_injection.py` (empty/None do nothing)._

#### Scenario: Mode selection follows configuration
- **WHEN** `copy_to_clipboard` is enabled
- **THEN** the engine SHALL route through the clipboard path, and SHALL route through the keystroke path when it is disabled

_Tier: unit-pure — `test_injection.py` (clipboard vs keystroke mode)._

### Requirement: Keystroke permission failure is detected and surfaced
The injection engine SHALL detect when a synthetic keystroke is rejected by
the OS (on macOS, osascript error `1002` / errAEEventNotPermitted from
`System Events`) and SHALL surface it to the user with an actionable
remediation, rather than failing silently while the clipboard appears to work.
The detection SHALL apply to both the clipboard-paste path (the `Cmd+V`
keystroke) and the direct-keystroke path.

#### Scenario: Denied paste keystroke is surfaced
- **WHEN** the clipboard is set successfully but the paste keystroke is denied
  with osascript error `1002`
- **THEN** the engine SHALL log a warning identifying the permission failure
  and SHALL present a user-visible notification with remediation (grant
  Accessibility/Automation to the current bundle, or run `tccutil reset`)

#### Scenario: Denied direct keystroke is surfaced
- **WHEN** keystroke injection mode is active and the keystroke is denied with
  osascript error `1002`
- **THEN** the engine SHALL log a warning and present the same user-visible
  remediation rather than reporting success

_Tier: unit-mocked — `subprocess` return code + stderr patched to emit `1002`._

### Requirement: Startup probe validates the keystroke path
The startup permission check SHALL validate that synthetic keystrokes are
actually permitted, not merely that a benign Apple-event query succeeds. A
probe that only confirms a non-keystroke query (e.g. `System Events return
name`) SHALL NOT be reported as "Automation authorized" when the keystroke
path is still denied.

#### Scenario: Benign query passes but keystroke is denied
- **WHEN** the benign `return name` query to System Events succeeds but a
  keystroke probe is denied with `1002`
- **THEN** the startup check SHALL report the keystroke path as not authorized
  and SHALL emit the remediation hint, not a false "authorized"

#### Scenario: Keystroke path fully authorized
- **WHEN** both the query and the keystroke probe succeed
- **THEN** the startup check SHALL report keystroke injection as authorized

_Tier: unit-mocked — `subprocess.run` results patched per branch._

### Requirement: Injected text is never interpreted as code
Text injection SHALL deliver transcribed content as literal data, never as executable AppleScript (or any shell/script language), regardless of the characters it contains.

#### Scenario: Backslashes and quotes are delivered verbatim
- **WHEN** transcribed text containing `"`, `\`, or AppleScript metacharacters is injected on macOS
- **THEN** the exact text SHALL be delivered to the clipboard / focused field and no part of it SHALL be parsed or executed as AppleScript

#### Scenario: Text reaches the injector via stdin or argv
- **WHEN** the macOS injector hands text to `osascript`/`pbcopy`
- **THEN** the text SHALL be passed via stdin or argv, never interpolated into an `osascript -e` script string

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


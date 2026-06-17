# text-injection Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

NOTE: pure injection behaviors tested today but not yet specced — quote escaping,
empty-text no-op, clipboard/keystroke mode switch (`test_injection.py`,
`unit-pure`). Add as requirements in a follow-up (candidate for step C).

## Requirements
### Requirement: Text Injection via System Services
The injection engine SHALL provide a mechanism to input transcribed text into the active application using system-level automation (e.g., via `osascript`).

#### Scenario: Successful Text Injection
- **WHEN** a transcription is completed and text injection is enabled
- **THEN** the engine SHALL inject the transcribed text into the currently focused application field

_Tier: macos-real — `test_injection.py` mocks `subprocess`, so `osascript` never actually runs; green does NOT prove text reaches the focused app. Deferred to step A._

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


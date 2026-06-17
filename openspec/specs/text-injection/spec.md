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


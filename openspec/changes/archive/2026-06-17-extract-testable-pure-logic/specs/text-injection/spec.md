## ADDED Requirements

### Requirement: Pure injection input handling
The injection engine SHALL apply deterministic, unit-tested input handling before any system call: it SHALL escape double quotes in the text destined for `osascript`, SHALL do nothing when the text is empty, and SHALL select the clipboard path versus the keystroke path based on the `copy_to_clipboard` setting. These behaviors SHALL be verifiable without invoking `osascript`.

#### Scenario: Double quotes are escaped
- **WHEN** the text to inject contains double-quote characters
- **THEN** the engine SHALL escape them before constructing the `osascript` command

_Tier: unit-pure._

#### Scenario: Empty text is a no-op
- **WHEN** the text to inject is empty
- **THEN** the engine SHALL perform no injection and SHALL NOT spawn a process

_Tier: unit-pure._

#### Scenario: Mode selection follows configuration
- **WHEN** `copy_to_clipboard` is enabled
- **THEN** the engine SHALL route through the clipboard path, and SHALL route through the keystroke path when it is disabled

_Tier: unit-pure._

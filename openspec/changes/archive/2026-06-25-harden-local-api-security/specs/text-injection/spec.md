## ADDED Requirements

### Requirement: Injected text is never interpreted as code
Text injection SHALL deliver transcribed content as literal data, never as executable AppleScript (or any shell/script language), regardless of the characters it contains.

#### Scenario: Backslashes and quotes are delivered verbatim
- **WHEN** transcribed text containing `"`, `\`, or AppleScript metacharacters is injected on macOS
- **THEN** the exact text SHALL be delivered to the clipboard / focused field and no part of it SHALL be parsed or executed as AppleScript

#### Scenario: Text reaches the injector via stdin or argv
- **WHEN** the macOS injector hands text to `osascript`/`pbcopy`
- **THEN** the text SHALL be passed via stdin or argv, never interpolated into an `osascript -e` script string

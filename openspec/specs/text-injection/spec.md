# text-injection Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.
## Requirements
### Requirement: Text Injection via System Services
The injection engine SHALL provide a mechanism to input transcribed text into the active application using system-level automation (e.g., via `osascript`).

#### Scenario: Successful Text Injection
- **WHEN** a transcription is completed and text injection is enabled
- **THEN** the engine SHALL inject the transcribed text into the currently focused application field

### Requirement: Clipboard Integration
The injection engine SHALL support an option to copy the transcribed text to the system clipboard instead of (or in addition to) direct keystroke injection.

#### Scenario: Clipboard Copy
- **WHEN** the "copy to clipboard" setting is enabled and a transcription completes
- **THEN** the engine SHALL update the system clipboard with the transcribed text


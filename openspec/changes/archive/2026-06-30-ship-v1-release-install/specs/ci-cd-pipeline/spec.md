## ADDED Requirements

### Requirement: Install scripts do not require sox
The install scripts (`install.sh`, `bootstrap.sh`) SHALL NOT require or gate on `sox`, since the audio backend uses sounddevice/PortAudio.

#### Scenario: Clean machine without sox
- **WHEN** the one-liner installer runs on a machine that does not have `sox`
- **THEN** it SHALL proceed and complete the install (no sox check, no abort)

### Requirement: One-liner install succeeds under curl | bash
The bootstrap installer SHALL complete successfully when piped from `curl` (a non-interactive, non-TTY shell), without a prompt that defaults to aborting.

#### Scenario: Non-interactive install
- **WHEN** `bootstrap.sh` runs via `curl … | bash` with no controlling TTY
- **THEN** it SHALL NOT block on or abort due to an unanswered prompt

### Requirement: Chosen Whisper model takes effect
When the user sets `WHISPER_MODEL`, the installed daemon SHALL use that model rather than silently falling back to the default.

#### Scenario: WHISPER_MODEL=medium
- **WHEN** the user installs with `WHISPER_MODEL=medium`
- **THEN** the daemon SHALL load the `medium` model (the value SHALL be persisted to config or read at load), not the default `small`

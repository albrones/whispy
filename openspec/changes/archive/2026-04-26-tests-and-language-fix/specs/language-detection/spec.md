## ADDED Requirements

### Requirement: Auto-detect language reliability
The system MUST reliably detect the spoken language when `language` is set to `"auto"` in the config.

#### Scenario: Auto-detect on short audio
- **WHEN** a recording of 1-2 seconds is transcribed with `language="auto"`
- **THEN** the language is correctly detected and transcribed

#### Scenario: Auto-detect on long audio
- **WHEN** a recording of 10+ seconds is transcribed with `language="auto"`
- **THEN** the language is correctly detected and transcribed

#### Scenario: Auto-detect switches between languages
- **WHEN** recordings in different languages are transcribed sequentially with `language="auto"`
- **THEN** each recording is transcribed in its detected language

#### Scenario: Auto-detect falls back gracefully
- **WHEN** language detection fails (e.g., silence-only audio)
- **THEN** transcription still returns a result (empty or best-guess) without crashing

### Requirement: Language config persistence
The system MUST persist the `language` config value across restarts.

#### Scenario: Language config survives restart
- **WHEN** the user selects a language (e.g., `"fr"`) in the UI
- **THEN** the value is saved to `~/.config/whispy/config.json` and restored on next launch

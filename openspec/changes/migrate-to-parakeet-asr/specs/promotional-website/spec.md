## MODIFIED Requirements

### Requirement: Value proposition and content sections
The promotional page SHALL communicate Whispy's purpose as a cross-platform (macOS and Linux/X11) local voice-dictation tool and route visitors to install and source. Where the page names the transcription engine, it SHALL name Parakeet, not faster-whisper.

#### Scenario: Hero communicates the product
- **WHEN** a visitor views the page
- **THEN** the hero presents the product name "Whispy" and a concise tagline describing local, cross-platform (macOS and Linux/X11) voice dictation — not macOS-only

#### Scenario: Privacy copy names the current model
- **WHEN** a visitor reads the privacy / local-processing statement
- **THEN** it SHALL attribute local transcription to `nvidia/parakeet-tdt-0.6b-v3` and SHALL NOT mention faster-whisper or Whisper

#### Scenario: Trigger described as configurable
- **WHEN** the page references the push-to-talk key
- **THEN** it describes a configurable trigger key rather than a hard-coded Fn-only key, noting the platform defaults (Fn on macOS, Right Ctrl on Linux)

#### Scenario: Required content sections present
- **WHEN** the page is rendered
- **THEN** it includes feature highlights, a "how it works" flow, a privacy/local-processing statement, and an install call-to-action

#### Scenario: Install instructions are cross-platform and accurate
- **WHEN** a visitor reads the install section
- **THEN** it presents both a macOS and a Linux/X11 install path, states that audio capture uses `sounddevice`/PortAudio, and does NOT list `sox` as a requirement

#### Scenario: Links to the repository
- **WHEN** a visitor wants the source or install instructions
- **THEN** the page links to the GitHub repository `https://github.com/albrones/whispy`

### Requirement: Site copy and demo match the app's default language
The site SHALL depict only menus and settings that exist in the shipped app. The animated menu-bar demo SHALL NOT show a Model submenu or a Language submenu, because neither exists after the backend swap.

#### Scenario: Demo dropdown shows no removed settings
- **WHEN** the animated menu-bar demo is rendered
- **THEN** its dropdown SHALL contain no "Model" row and no "Language" row

#### Scenario: No copy implies a choice of model size
- **WHEN** feature cards and body copy are read
- **THEN** none SHALL offer a choice between transcription models, model sizes, or quality tiers

## ADDED Requirements

### Requirement: Site carries model attribution
Because the transcription model is CC-BY-4.0, the page SHALL credit NVIDIA for `parakeet-tdt-0.6b-v3` alongside its existing licence statement.

#### Scenario: Attribution appears near the licence statement
- **WHEN** a visitor reads the page's licence information
- **THEN** it SHALL state that Whispy is GPL-3.0 and credit the model to NVIDIA under CC-BY-4.0

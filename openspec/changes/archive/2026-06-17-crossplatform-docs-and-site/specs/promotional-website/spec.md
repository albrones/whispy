## MODIFIED Requirements

### Requirement: Value proposition and content sections
The promotional page SHALL communicate Whispy's purpose as a cross-platform
(macOS and Linux/X11) local voice-dictation tool and route visitors to install
and source.

#### Scenario: Hero communicates the product
- **WHEN** a visitor views the page
- **THEN** the hero presents the product name "Whispy" and a concise tagline describing local, cross-platform (macOS and Linux/X11) voice dictation — not macOS-only

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

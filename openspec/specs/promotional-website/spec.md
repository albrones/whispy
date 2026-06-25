# promotional-website Specification

## Purpose
TBD - created by archiving change promotional-website. Update Purpose after archive.
## Requirements
### Requirement: Static promotional landing page
The system SHALL provide a static, dependency-free promotional website under `website/` that renders without any build step or runtime server-side processing.

#### Scenario: Page opens standalone
- **WHEN** `website/index.html` is opened directly in a browser (file:// or static host)
- **THEN** the page renders fully without requiring a build step, package install, or backend

#### Scenario: No external runtime requests for core rendering
- **WHEN** the page loads with no network access
- **THEN** core layout, branding, and logo render correctly because all required assets are local

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

### Requirement: Brand-consistent responsive presentation
The promotional page SHALL use the Whispy brand identity and adapt to viewport size.

#### Scenario: Brand color applied
- **WHEN** the page is styled
- **THEN** the Whispy brand green `#24bf9e` is used as the primary accent on a dark theme

#### Scenario: Responsive layout
- **WHEN** the page is viewed on a narrow (mobile) or wide (desktop) viewport
- **THEN** the layout adapts without horizontal overflow

#### Scenario: Animation respects reduced-motion
- **WHEN** the user has `prefers-reduced-motion` enabled
- **THEN** the decorative waveform animation is disabled

### Requirement: Site states the correct license
The promotional website SHALL state the project's actual license (GPLv3), consistent with `LICENSE`, the README, and the Homebrew formula.

#### Scenario: License is displayed
- **WHEN** the site references the project license
- **THEN** it SHALL say GPLv3 (and SHALL NOT claim MIT)

### Requirement: Social preview image renders
The site SHALL provide an Open Graph / Twitter card image in a format social platforms render (PNG/JPG, not SVG).

#### Scenario: Link is shared on social media
- **WHEN** a page URL is shared and a platform fetches `og:image` / `twitter:image`
- **THEN** the referenced image SHALL be a PNG/JPG that renders (not an SVG that shows blank)


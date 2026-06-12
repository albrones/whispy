## ADDED Requirements

### Requirement: Static promotional landing page
The system SHALL provide a static, dependency-free promotional website under `website/` that renders without any build step or runtime server-side processing.

#### Scenario: Page opens standalone
- **WHEN** `website/index.html` is opened directly in a browser (file:// or static host)
- **THEN** the page renders fully without requiring a build step, package install, or backend

#### Scenario: No external runtime requests for core rendering
- **WHEN** the page loads with no network access
- **THEN** core layout, branding, and logo render correctly because all required assets are local

### Requirement: Value proposition and content sections
The promotional page SHALL communicate Whispy's purpose and route visitors to install and source.

#### Scenario: Hero communicates the product
- **WHEN** a visitor views the page
- **THEN** the hero presents the product name "Whispy" and a concise tagline describing local macOS voice dictation

#### Scenario: Required content sections present
- **WHEN** the page is rendered
- **THEN** it includes feature highlights, a "how it works" flow, a privacy/local-processing statement, and an install call-to-action

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

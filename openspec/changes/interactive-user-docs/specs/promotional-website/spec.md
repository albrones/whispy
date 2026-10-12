## ADDED Requirements

### Requirement: Landing page links to the documentation
The landing page header navigation SHALL include a "Docs" link to the documentation site, using a relative URL, and the install section SHALL link to the docs' install page for the step-by-step guide.

#### Scenario: Docs link in the header
- **WHEN** a visitor views `website/index.html`
- **THEN** the header navigation contains a "Docs" link whose target is `docs/` relative to the page

#### Scenario: Install section points to the full guide
- **WHEN** a visitor reads the install section
- **THEN** it links to the docs' install page

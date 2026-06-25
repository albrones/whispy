## ADDED Requirements

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

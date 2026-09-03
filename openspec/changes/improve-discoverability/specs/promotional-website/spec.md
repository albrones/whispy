## ADDED Requirements

### Requirement: Canonical URL on a stable custom domain

The site SHALL be served from a stable custom domain (not an auto-generated
hosting subdomain) and SHALL declare that domain as canonical, so search engines
index a single authoritative origin.

#### Scenario: Canonical link present

- **WHEN** `website/index.html` is rendered
- **THEN** the `<head>` SHALL contain a `<link rel="canonical">` whose `href` is the site's custom-domain URL

#### Scenario: Single indexable origin

- **WHEN** the site is reachable on more than one host (e.g. `www` and apex, or a hosting-preview subdomain)
- **THEN** non-canonical hosts SHALL redirect to the canonical host so only one origin is indexed

### Requirement: Structured data for app discovery

The site SHALL embed `SoftwareApplication` JSON-LD structured data so search
engines can surface Whispy as an application (name, supported OS, price, license).

#### Scenario: SoftwareApplication schema present and valid

- **WHEN** `website/index.html` is rendered
- **THEN** the `<head>` SHALL include a `<script type="application/ld+json">` block whose JSON parses and declares `@type` `SoftwareApplication` with at least `name`, `operatingSystem`, `offers` (price `0`), and a `license`/`url` field

### Requirement: Crawler files

The site SHALL provide `robots.txt` and `sitemap.xml` at the site root so
crawlers can discover and index the page.

#### Scenario: robots.txt served and references the sitemap

- **WHEN** a crawler requests `/robots.txt`
- **THEN** the file SHALL be served and SHALL include a `Sitemap:` directive pointing at the canonical `sitemap.xml` URL

#### Scenario: sitemap lists the canonical URL

- **WHEN** a crawler requests `/sitemap.xml`
- **THEN** the file SHALL be served and SHALL list the site's canonical URL

## MODIFIED Requirements

### Requirement: Social preview image renders

The site SHALL provide an Open Graph / Twitter card image in a format social
platforms render (PNG/JPG, not SVG), referenced by an **absolute** URL so
crawlers that do not resolve relative paths still fetch it.

#### Scenario: Link is shared on social media

- **WHEN** a page URL is shared and a platform fetches `og:image` / `twitter:image`
- **THEN** the referenced image SHALL be a PNG/JPG that renders (not an SVG that shows blank)

#### Scenario: Social image URL is absolute

- **WHEN** the `og:image` and `twitter:image` meta tags are read
- **THEN** their values SHALL be absolute `http(s)://` URLs on the canonical domain, not relative paths

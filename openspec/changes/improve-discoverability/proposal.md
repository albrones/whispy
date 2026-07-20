## Why

Whispy is finished enough to promote, but it is hard to find. The site is live
on an auto-generated Vercel subdomain (`whispy-dun.vercel.app`) — unmemorable,
untrustworthy to crawlers, and carrying no keyword. The repository has **zero
GitHub topics**, so it is invisible on GitHub's topic pages and search — the
primary discovery channel for a developer tool. On the SEO side the page has a
solid base (title, description, OG/Twitter tags, semantic headings) but is
missing the pieces that actually move ranking and social sharing: a canonical
URL, absolute social-image URLs, `SoftwareApplication` structured data,
`robots.txt`, and a `sitemap.xml`.

For a niche open-source utility, organic Google SEO is a minor channel; the high-
leverage channels are GitHub itself, package managers, and curated lists. This
change fixes the cheap, high-payoff gaps first and gets the SEO fundamentals
right so the site is worth linking to.

## What Changes

**Website / SEO (spec-guarded):**
- Attach a real custom domain to the Vercel project and make it the canonical host.
- Add `<link rel="canonical">` pointing at the canonical domain.
- Make `og:image` / `twitter:image` **absolute** URLs so social cards render.
- Add `SoftwareApplication` JSON-LD structured data (name, OS, price 0, GPLv3
  license, screenshot) for Google app rich results.
- Add `robots.txt` and `sitemap.xml` referencing the canonical domain.
- Add a raster favicon fallback (PNG/ICO) alongside the existing SVG icon.

**GitHub / off-site (operational, tracked in tasks — not spec requirements):**
- Add GitHub repository topics (`whisper`, `speech-to-text`, `dictation`,
  `macos`, `linux`, `voice`, `faster-whisper`, `privacy`, `local-first`,
  `menu-bar-app`).
- Point the repo "About" homepage at the new canonical domain.
- Add site link + license/platform badges to the top of the README.
- Submit entries to curated lists (awesome-* PRs, alternativeto.net) and prepare
  a launch post (HN / relevant subreddits). These are outreach actions, checklist
  only — not verifiable code.

## Capabilities

### New Capabilities
<!-- none: this extends the existing promotional-website capability -->

### Modified Capabilities
- `promotional-website`: the site gains SEO/discoverability requirements — a
  canonical URL on a stable custom domain, absolute social-image URLs,
  `SoftwareApplication` structured data, and crawler files (`robots.txt`,
  `sitemap.xml`). The social-preview requirement is tightened to require an
  absolute URL (a relative `og:image` breaks most crawlers).

## Impact

- Files: `website/index.html` (canonical, absolute OG URLs, JSON-LD, favicon
  link), new `website/robots.txt`, new `website/sitemap.xml`, new raster favicon
  asset under `website/assets/`, `vercel.json` (domain config if needed),
  `README.md` (badges + site link). GitHub topics + About URL set via `gh`/UI.
- Tests: extend `tests/test_website.py` — assert canonical tag, absolute
  `og:image`, presence of `SoftwareApplication` JSON-LD, and that `robots.txt` /
  `sitemap.xml` exist and reference the canonical domain.
- No new runtime dependencies; the site stays static and build-free.
- Blocking decision: the canonical **domain name** must be chosen/purchased
  before canonical URL, sitemap, and OG absolute URLs can be finalized.

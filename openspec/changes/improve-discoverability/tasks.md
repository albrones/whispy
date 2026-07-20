## 1. Canonical domain (blocking — decide first)

- [ ] 1.1 Choose and purchase a canonical domain (candidates: `whispy.app`, `getwhispy.com`, `whispy.sh`). Prefer `.app` — enforces HTTPS, reads as a native app
- [ ] 1.2 Add the domain to the Vercel `whispy` project and set it as the primary/canonical domain; verify DNS + HTTPS resolves
- [ ] 1.3 Configure the `www` (or apex) alias to 301-redirect to the single canonical host so there is one indexable origin
- [ ] 1.4 Record the chosen canonical URL as `CANONICAL_URL` used consistently below (canonical tag, sitemap, OG images)

## 2. SEO fundamentals in the page

- [x] 2.1 Add `<link rel="canonical" href="{CANONICAL_URL}/">` to `website/index.html` `<head>`
- [x] 2.2 Change `og:image` and `twitter:image` from `assets/og-image.png` to the absolute `{CANONICAL_URL}/assets/og-image.png`
- [x] 2.3 Add `SoftwareApplication` JSON-LD `<script type="application/ld+json">` in `<head>` with: `name` "Whispy", `applicationCategory` "UtilitiesApplication", `operatingSystem` "macOS, Linux", `offers` price `0` currency `USD`, `license` GPLv3 URL, `url` `{CANONICAL_URL}`, `screenshot` `{CANONICAL_URL}/assets/og-image.png`, `description` matching the meta description
- [x] 2.4 Add a raster favicon (`assets/favicon.png` 512×512 and/or `favicon.ico`) and reference it: `<link rel="icon" type="image/png" href="assets/favicon.png">` alongside the existing SVG link

## 3. Crawler files

- [x] 3.1 Create `website/robots.txt` allowing all crawlers and pointing `Sitemap:` at `{CANONICAL_URL}/sitemap.xml`
- [x] 3.2 Create `website/sitemap.xml` with the single canonical URL and a `<lastmod>` date
- [x] 3.3 Confirm Vercel serves both at the site root (they are in `outputDirectory: website`, so no config change expected — verify)

## 4. GitHub discoverability (operational)

- [x] 4.1 Add repo topics via `gh repo edit albrones/whispy --add-topic whisper --add-topic speech-to-text --add-topic dictation --add-topic macos --add-topic linux --add-topic voice --add-topic faster-whisper --add-topic privacy --add-topic local-first --add-topic menu-bar-app`
- [x] 4.2 Set the repo homepage: `gh repo edit albrones/whispy --homepage {CANONICAL_URL}`
- [x] 4.3 Add to the top of `README.md`: a one-line site link and shields.io badges (license GPLv3, platform macOS/Linux). Keep it minimal — no CI/coverage vanity badges
- [x] 4.4 Front-load the repo `--description` with the benefit before the tech ("Private, local voice dictation for macOS & Linux — hold a key, speak, and your words type into any app. Runs offline via faster-whisper.")

## 5. Off-site outreach (checklist only — no code)

- [ ] 5.1 Submit PRs to relevant `awesome-*` lists (awesome-macos, awesome-whisper, awesome-privacy, awesome-selfhosted-adjacent)
- [ ] 5.2 Create an alternativeto.net entry (positioned vs Wispr Flow, Dragon, macOS Dictation)
- [ ] 5.3 Draft a launch post for Hacker News (Show HN) and r/macapps / r/selfhosted; hold until domain + badges + JSON-LD are live

## 6. Tests & verification

- [x] 6.1 Extend `tests/test_website.py`: assert a `<link rel="canonical">` is present; assert `og:image` is an absolute `http(s)://` URL; assert a `SoftwareApplication` JSON-LD block exists and parses; assert `website/robots.txt` and `website/sitemap.xml` exist and contain the canonical host
- [x] 6.2 Run `./.venv/bin/pytest tests/test_website.py` — green (18 passed)
- [ ] 6.3 Validate the live page: Google Rich Results Test (SoftwareApplication detected), a social-card debugger (OG image renders), and `curl {CANONICAL_URL}/robots.txt` / `/sitemap.xml` return 200 — after next Vercel deploy

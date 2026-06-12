## Why

Whispy has no public-facing landing page. Anyone discovering the project lands directly on the GitHub README, which is dense and developer-oriented. A static promotional website gives Whispy a clear, polished entry point that communicates the value proposition (fast, private, local macOS dictation) at a glance and routes visitors to install instructions and the repository. It is also a prerequisite for the next TODO item (CI/CD deployment to Vercel).

## What Changes

- Add a self-contained static promotional website under `website/` (no build step, no runtime dependencies).
- Single landing page (`index.html`) with hero, feature highlights, "how it works", privacy section, models table, and install call-to-action.
- Brand-consistent styling (`styles.css`) using the Whispy brand green `#24bf9e` on a dark theme, matching the in-app waveform.
- A lightweight animated waveform demo (`script.js`) echoing the recording visualization, with `prefers-reduced-motion` support.
- An inline SVG/asset logo so the page renders with zero external requests.
- Responsive layout (mobile + desktop) and basic SEO/social meta tags.

## Capabilities

### New Capabilities
- `promotional-website`: A static, dependency-free promotional landing page that presents Whispy's value proposition, features, privacy stance, and install path, and links to the GitHub repository.

## Impact

- **New files**: `website/index.html`, `website/styles.css`, `website/script.js`, `website/assets/logo.svg`
- **New tests**: `tests/test_website.py` (validates page structure, brand presence, and that all locally-referenced assets exist)
- No changes to the daemon, packaging, or any runtime behavior
- No new Python or system dependencies

## Context

The website and docs are the first thing a prospective user reads. The review found the site itself well-built (accessible, secure, responsive, brand-consistent) but carrying two HIGH factual errors (license, sox) plus stale platform/spec text. `tests/test_website.py` currently asserts brand name, accent color, repo URL, sections, title/description, reduced-motion, and local-asset existence — it does not catch the MIT/GPL or sox contradictions, which is why they survived.

## Goals / Non-Goals

**Goals:**
- Correct, non-contradictory user-facing claims (license, audio backend, supported platforms).
- Social previews that render.
- Regression tests so these specific errors can't return silently.

**Non-Goals:**
- Redesigning the site or its visual language.
- The actual tagged release (owned by `ship-v1-release-install`).
- Removing the sox *gate* from install scripts (also owned by `ship-v1-release-install`); here it is only the sox *documentation* claims.

## Decisions

### License text
Change the single "MIT-licensed" string to "GPLv3-licensed" to match `LICENSE`, README, CONTRIBUTING, and the formula. Add a `test_website.py` assertion for the GPLv3 string (and that "MIT" does not appear in a license context).

### OG image
Add a static PNG/JPG (e.g. derived from the logo + wordmark at 1200×630) and point `og:image`/`twitter:image` at it. SVG is invalid for these cards. Keep the SVG logo for in-page use.

### sox / platform docs
`CONTRIBUTING.md`: remove `brew install sox`; change "macOS only" to macOS + Linux (X11); add Linux/distro to the bug-report ask. `docs/SPECIFICATION.md`: replace sox-as-backend references with sounddevice/PortAudio, or mark those sections obsolete with a pointer to the current backend. Coordinate with `ship-v1-release-install`, which removes the sox gate from the scripts/formula.

## Risks / Trade-offs

- The OG image is a new binary asset; keep it small and inline-free (CSP on the site blocks externals anyway).
- ROADMAP release status depends on `ship-v1-release-install` landing first — sequence accordingly.

## Migration Plan

Docs/website-only; no code, config, or API impact. Website redeploys via the existing `deploy-website.yml` on push.

## Open Questions

- Whether to also fix `docs/SPECIFICATION.md` fully now or just mark it obsolete — leaning update the sox references, low effort.

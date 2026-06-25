## Why

User-facing communication has factual errors that ship straight to end users:

- **Wrong license on the public website**: `website/index.html` says "MIT-licensed", but the project is GPLv3 (`LICENSE`, README, `CONTRIBUTING.md`, and the formula's `license "GPL-3.0-or-later"` all agree on GPLv3). A wrong license claim on the public site is a real legal/trust problem.
- **Stale sox claims in docs**: `CONTRIBUTING.md` tells contributors to `brew install sox` and `docs/SPECIFICATION.md` still documents sox as the audio backend, though the backend migrated to sounddevice/PortAudio.
- **Stale platform claim**: `CONTRIBUTING.md` says "Whispy currently targets macOS only", contradicting the now-advertised macOS + Linux (X11) support and the bug-report template that asks only for "macOS version".
- **Broken social previews**: `og:image` / `twitter:image` point at `assets/logo.svg`; Open Graph and Twitter cards do not render SVG, so social shares show a blank image.
- **`docs/ROADMAP.md`** lists "Tagged release + notes" as unchecked — a signal v0.1.0 is not actually released, while the site/README hand out the `brew` one-liner as if the tap were live (the release itself is handled by `ship-v1-release-install`).

The rebrand is otherwise complete — no stale product name leaked anywhere (only "Whisper"/"faster-whisper", the model, which is correct). The website is clean, accessible, and secure (no external scripts, no inline handlers, no `innerHTML`, reduced-motion honored).

## What Changes

- Fix the website license text: "MIT-licensed" → "GPLv3-licensed".
- Provide a real PNG/JPG Open Graph image and point `og:image`/`twitter:image` at it.
- Remove sox from `CONTRIBUTING.md` dev setup; update `docs/SPECIFICATION.md` to reflect the sounddevice/PortAudio backend (or mark the sox sections obsolete).
- Update `CONTRIBUTING.md` "macOS only" → macOS + Linux (X11); update the bug-report template to ask for Linux/distro too.
- Tighten `tests/test_website.py` to catch the license string and a sox-contradiction so these regressions can't silently return.

## Capabilities

### Modified Capabilities
- `promotional-website`: the site SHALL state the correct license (GPLv3) and SHALL provide a social-preview image that renders (non-SVG).

## Impact

- `website/index.html` — license text; OG/Twitter image tags.
- `website/assets/` — add a PNG/JPG OG image.
- `CONTRIBUTING.md` — drop sox; macOS-only → macOS + Linux; bug-report template.
- `docs/SPECIFICATION.md` — sox → sounddevice/PortAudio (or mark obsolete).
- `docs/ROADMAP.md` — reflect release status once `ship-v1-release-install` completes.
- `tests/test_website.py` — assert GPLv3 and no sox claim.

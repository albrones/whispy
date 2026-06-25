## 1. Website license + social preview (index.html)

- [x] 1.1 Change "MIT-licensed" → "GPLv3-licensed"
- [x] 1.2 Add a PNG/JPG Open Graph image (1200×630) under `website/assets/`
- [x] 1.3 Point `og:image` / `twitter:image` at the PNG/JPG (not the SVG)

## 2. Contributor + spec docs

- [x] 2.1 Remove `brew install sox` from `CONTRIBUTING.md` dev setup
- [x] 2.2 Change "macOS only" → macOS + Linux (X11) in `CONTRIBUTING.md`
- [x] 2.3 Add Linux/distro to the bug-report template ask
- [x] 2.4 Update `docs/SPECIFICATION.md` sox references to sounddevice/PortAudio (or mark obsolete)

## 3. Roadmap

- [x] 3.1 Reflect the actual release status in `docs/ROADMAP.md` (after `ship-v1-release-install` lands the tag)

## 4. Tests

- [x] 4.1 `test_website.py` asserts the GPLv3 license string and that no MIT license claim appears
- [x] 4.2 `test_website.py` asserts no sox claim on the site

## 5. Verification

- [x] 5.1 Run the full test suite; confirm no regression
- [x] 5.2 `openspec validate fix-user-facing-docs --strict`

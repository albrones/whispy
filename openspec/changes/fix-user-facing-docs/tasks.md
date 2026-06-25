## 1. Website license + social preview (index.html)

- [ ] 1.1 Change "MIT-licensed" → "GPLv3-licensed"
- [ ] 1.2 Add a PNG/JPG Open Graph image (1200×630) under `website/assets/`
- [ ] 1.3 Point `og:image` / `twitter:image` at the PNG/JPG (not the SVG)

## 2. Contributor + spec docs

- [ ] 2.1 Remove `brew install sox` from `CONTRIBUTING.md` dev setup
- [ ] 2.2 Change "macOS only" → macOS + Linux (X11) in `CONTRIBUTING.md`
- [ ] 2.3 Add Linux/distro to the bug-report template ask
- [ ] 2.4 Update `docs/SPECIFICATION.md` sox references to sounddevice/PortAudio (or mark obsolete)

## 3. Roadmap

- [ ] 3.1 Reflect the actual release status in `docs/ROADMAP.md` (after `ship-v1-release-install` lands the tag)

## 4. Tests

- [ ] 4.1 `test_website.py` asserts the GPLv3 license string and that no MIT license claim appears
- [ ] 4.2 `test_website.py` asserts no sox claim on the site

## 5. Verification

- [ ] 5.1 Run the full test suite; confirm no regression
- [ ] 5.2 `openspec validate fix-user-facing-docs --strict`

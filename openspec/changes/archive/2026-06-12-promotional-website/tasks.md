## 1. Scaffold

- [x] 1.1 Create `website/` directory structure
- [x] 1.2 Add `website/assets/logo.svg` brand logo (inline-renderable, zero external requests)

## 2. Page Markup

- [x] 2.1 Create `website/index.html` with semantic structure (header/nav, hero, features, how-it-works, privacy, models, install CTA, footer)
- [x] 2.2 Add SEO + Open Graph / Twitter meta tags and `<title>`
- [x] 2.3 Link to the GitHub repository (`https://github.com/albrones/whispy`) in nav and CTA

## 3. Styling

- [x] 3.1 Create `website/styles.css` with the brand green `#24bf9e` on a dark theme
- [x] 3.2 Make the layout responsive (mobile + desktop) via CSS, no framework
- [x] 3.3 Style the models table

## 4. Interaction

- [x] 4.1 Create `website/script.js` with an animated waveform hero demo
- [x] 4.2 Respect `prefers-reduced-motion` (no animation when the user opts out)

## 5. Testing

- [x] 5.1 Create `tests/test_website.py` validating page existence, brand name/color, required sections, and GitHub link
- [x] 5.2 Add a test asserting every locally-referenced asset (css/js/svg) exists on disk
- [x] 5.3 Run the full test suite to verify no regression

## 6. Wrap-up

- [x] 6.1 Validate the change with `openspec validate promotional-website --strict`
- [x] 6.2 Archive the change with `openspec archive`
- [x] 6.3 Mark TODO.md "Static promotional website" task as done `[x]`
- [x] 6.4 Commit

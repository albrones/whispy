## 1. Write the tutorial

- [x] 1.1 Create `docs/homebrew.md` with sections: tap repo layout, formula anatomy, release pipeline, required secret, cutting a release, manual bump, user install/upgrade/uninstall
- [x] 1.2 Verify every claim against `packaging/homebrew/whispy.rb` and `.github/workflows/release.yml`

## 2. Add the formula guard test

- [x] 2.1 Create `tests/test_homebrew_formula.py` asserting required fields (`desc`, `homepage`, `url`, `sha256`, `license`, `service do`, `test do`, `depends_on "python@3.12"`, `depends_on "sox"`)
- [x] 2.2 Assert exactly one `url` line and one `sha256` line (the lines `release.yml` rewrites)

## 3. Verification

- [x] 3.1 Run the full test suite; confirm no regression
- [x] 3.2 `ruff check` / `ruff format --check` on the new test
- [x] 3.3 `openspec validate document-homebrew-integration --strict`

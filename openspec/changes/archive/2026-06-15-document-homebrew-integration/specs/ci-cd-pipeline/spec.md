## ADDED Requirements

### Requirement: Homebrew release pipeline is documented
The Homebrew integration — tap repo layout, formula anatomy, the release-on-tag pipeline, required secrets, how to cut a release, manual formula bump, and the end-user install/upgrade/uninstall flow — SHALL be documented in a maintainer tutorial.

#### Scenario: Tutorial exists and covers the pipeline
- **WHEN** a maintainer needs to set up the tap, cut a release, or fix the formula
- **THEN** `docs/homebrew.md` SHALL describe the tap repo, the formula, the `release.yml` tag-triggered tap bump, the `HOMEBREW_TAP_TOKEN` secret, and the user install command `brew install albrones/whispy/whispy`

### Requirement: Homebrew formula structure is guarded by a test
The Homebrew formula `packaging/homebrew/whispy.rb` SHALL retain the fields the documentation and release pipeline depend on, verified by an automated test.

#### Scenario: Formula has required fields
- **WHEN** the formula test runs
- **THEN** it SHALL assert the formula declares `desc`, `homepage`, `url`, `sha256`, `license`, a `service do` block, and a `test do` block, and depends on `python@3.12` and `sox`

#### Scenario: Release-bumped fields are present for the pipeline to patch
- **WHEN** the formula test runs
- **THEN** it SHALL assert the formula contains a single `url` line and a single `sha256` line (the lines `release.yml` rewrites per release)

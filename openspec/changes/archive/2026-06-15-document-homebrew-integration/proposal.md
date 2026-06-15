## Why

Whispy ships a Homebrew formula (`packaging/homebrew/whispy.rb`) and a release workflow (`release.yml`) that auto-bumps a separate tap repo on each `v*` tag, but the process is only documented as scattered comments inside those files. A maintainer setting up the tap, cutting a release, or fixing a broken formula has no single tutorial to follow, and `docs/deployment.md` already links to a `docs/homebrew.md` that does not yet exist.

## What Changes

- Add `docs/homebrew.md` — an end-to-end tutorial covering: the tap repo layout, the formula's anatomy (venv-in-libexec install, service block, caveats, permissions), how the release pipeline computes the tarball sha256 and bumps the tap, the required `HOMEBREW_TAP_TOKEN` secret, how to cut a release (tag push), how to bump the formula by hand, and the end-user install/upgrade/uninstall flow.
- Add a structural unit test that pins the formula's required fields so the tutorial and the formula cannot silently drift apart.

## Capabilities

### Modified Capabilities
- `ci-cd-pipeline`: add requirements that the Homebrew release pipeline be documented in a maintainer tutorial and that the formula's required fields be guarded by a test (the release-on-tag and tap-bump behavior already exists in `release.yml`; this makes it specced and documented).

## Impact

- `docs/homebrew.md` — new tutorial (resolves the dangling link from `docs/deployment.md`).
- `tests/test_homebrew_formula.py` — new structural test of `packaging/homebrew/whispy.rb`.
- No source or workflow changes.

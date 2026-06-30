## REMOVED Requirements

### Requirement: Homebrew release pipeline is documented

**Reason**: The Homebrew formula is dropped (a formula is the wrong tool for a GUI `.app`; the macOS install consolidates on the signed `Whispy.app`). The tap, `release.yml` tap-bump job, `HOMEBREW_TAP_TOKEN` secret, and `docs/homebrew.md` are removed with it. A Homebrew **Cask** may return as future work, gated on notarization.

### Requirement: Homebrew formula structure is guarded by a test

**Reason**: `packaging/homebrew/whispy.rb` is deleted, so the formula-structure test that guarded its required fields no longer has a subject.

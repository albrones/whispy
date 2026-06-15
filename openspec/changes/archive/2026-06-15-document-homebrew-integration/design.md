## Context

The Homebrew bits exist and work: `packaging/homebrew/whispy.rb` is the canonical formula, and `release.yml` (on a `v*` tag) creates a GitHub release, computes the source-tarball sha256, copies the canonical formula into the `albrones/homebrew-whispy` tap, patches `url` + `sha256`, and pushes. The knowledge lives only in code comments. `docs/deployment.md` (added earlier) already links to `docs/homebrew.md`, which is currently a dead link.

## Goals / Non-Goals

**Goals:**
- One maintainer-facing tutorial that explains the whole Homebrew flow.
- A test that pins the formula fields the docs and pipeline rely on.

**Non-Goals:**
- Changing the formula, the release workflow, or the tap repo.
- Submitting to homebrew-core (the formula is explicitly a personal-tap design that pip-installs into a libexec venv).

## Decisions

### Tutorial content, derived from the actual files
The tutorial documents what `whispy.rb` and `release.yml` already do — no aspirational steps. Sections: tap repo layout, formula anatomy (venv-in-libexec rationale, `service do`, caveats/permissions), the release pipeline step-by-step, the `HOMEBREW_TAP_TOKEN` secret, cutting a release via tag, manual formula bump (the `curl | shasum -a 256` recipe already in the formula comments), and the user install/upgrade/uninstall flow.

### Test approach: text assertions, no Ruby
The repo has no Ruby toolchain in CI, so the test reads `whispy.rb` as text and asserts the presence of required fields and exactly one `url`/`sha256` line (the lines the pipeline rewrites with a `count=1` regex). This guards the pipeline's assumption and keeps the docs honest without adding a Ruby dependency. Mirrors the existing `tests/test_website.py` / `tests/test_deploy_workflow.py` structural-test style.

## Risks / Trade-offs

- A text-based formula test won't catch Ruby syntax errors. Acceptable: `brew install` in a real environment is the syntax check, and the test's job is to protect the fields the pipeline patches.

## Migration Plan

Docs + test only. No migration.

## Open Questions

- None.

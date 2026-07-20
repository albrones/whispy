## Why

A completed CI/test audit found that the pipeline in `.github/workflows/ci.yml`
and `.github/workflows/release.yml` has drifted from what it claims to verify:

1. **The macOS real-seam tests never run, even on the macOS runner.**
   `ci.yml:29-53`'s `test` job runs on `macos-latest`, but `pyproject.toml:52`
   sets `addopts = "-m 'not macos and not linux'"` globally, so the 20 tests
   marked `macos` (`tests/test_e2e_smoke.py`, `tests/test_transcription_quality.py`,
   `tests/test_waveform.py` — verified: 4 + 5 + 11 = 20) are silently
   *deselected*, not skipped. No job anywhere passes `-m macos`. A green CI
   run proves nothing about the event tap, real audio capture, real
   transcription quality, or the waveform overlay.
2. **There is no Linux runner at all.** Every job runs on `macos-latest`. The
   default (mocked/unit) test tier that exercises `src/whispy/platform/linux/*`
   (`pynput` hotkey, `pystray` tray, `xdotool` injection path) has only ever
   executed under macOS-side mocking, never on an actual Linux interpreter/OS.
3. **`ci.yml:43-44` installs a dependency the project no longer has.**
   `brew install sox` runs on every one of the three matrix legs, but `sox`
   was removed when the audio backend moved to `sounddevice`/PortAudio. The
   only guard test (`tests/test_install_scripts.py:38`) checks `install.sh`
   and `scripts/bootstrap.sh` for a `sox` gate — it has no visibility into
   `ci.yml`, so this drifted silently.
4. **`release.yml` has no dependency on tests or lint.** It fires on any
   `v*` tag push and calls `softprops/action-gh-release@v2` directly — a
   release can ship from a commit whose CI is red, or that was never tested
   at all if tagged off a branch.
5. **Coverage has no floor.** `ci.yml:53` passes `--cov` and
   `--cov-report=term-missing` but no `--cov-fail-under`, so coverage can
   regress silently. Locally, `pytest-cov` was not even installed in
   `.venv` despite being in the `[dev]` extra, and the checked-in `.coverage`
   file predates several deleted modules.
6. **No test-hang protection.** `pytest-timeout` is not a dependency and
   nothing bounds an individual test's runtime; a hang in a threaded or
   real-seam test blocks the job until the GitHub Actions job/step timeout
   (up to 6 hours by default) kills it.
7. **The shipped version is duplicated with no consistency check.**
   `pyproject.toml:8` (`version = "1.0.0"`) and
   `packaging/macos/setup_app.py:17` (`VERSION = "1.0.0"`) can drift
   independently — nothing in CI or the test suite compares them.

Re-running the audit's exact CI command locally (`pytest -v --tb=short
--cov=src/whispy --cov-report=term-missing`, after installing the missing
`pytest-cov`) confirms findings 1 and 5 directly: `618 passed, 1 skipped, 20
deselected`, total coverage `89%`.

## What Changes

- Add a dedicated macOS real-seam job that runs `pytest -m macos`, so the 20
  currently-deselected tests execute in CI. They are designed to skip
  cleanly (not fail) when a hosted runner lacks the Microphone/Input
  Monitoring TCC grant or the `say`/`sox` synthesis toolchain — skips are
  visible in the job log; deselection was not. A real failure (crash,
  exception) still fails the job.
- Add a Linux (`ubuntu-latest`) leg that runs the same default (mocked/unit)
  test tier as the macOS job, across the same Python version matrix, so
  `src/whispy/platform/linux/*` and any Linux-specific path/subprocess
  behavior actually executes on Linux. The `linux`-marked real-hardware tier
  (`tests/test_e2e_smoke_linux.py`) continues to require a live X11 session
  with real audio and is intentionally not run on hosted CI, per
  `openspec/specs/TESTING-TIERS.md`'s existing `linux-real` tier definition.
- Remove the `brew install sox` step from `ci.yml`'s `test` job matrix.
- Add `pytest-timeout` to the `[dev]` extra and configure a default
  per-test timeout, so a hang fails the test instead of blocking the job.
- Add a `--cov-fail-under` floor to the coverage invocation, set from a
  freshly measured baseline (89% on the default tier, verified above) minus
  a 5-point margin.
- Add a test that asserts `pyproject.toml`'s `[project].version` matches
  `packaging/macos/setup_app.py`'s `VERSION`, so drift fails the fast
  default-tier job on every push/PR instead of only surfacing at release
  time.
- Gate `release.yml` on the full CI suite passing for the tagged commit, via
  a reusable workflow (`workflow_call`) rather than a same-workflow `needs:`
  (not possible across files) or a `workflow_run` trigger (fragile SHA
  correlation — see `design.md`).
- Update `openspec/specs/TESTING-TIERS.md`'s `macos-real` row to reflect
  that it now runs in CI (skip-tolerant), while `linux-real` stays
  documented as local-only.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- **ci-cd-pipeline**: gains requirements for macOS real-seam test execution
  in CI, a Linux CI leg, release gating on CI, a coverage floor, test-hang
  protection, and version consistency; the existing "Install scripts do not
  require sox" requirement is broadened to also cover the CI workflow
  (`ci.yml` must not install `sox` either).

## Impact

- Affected files: `.github/workflows/ci.yml`, `.github/workflows/release.yml`,
  `pyproject.toml` (`[project.optional-dependencies].dev`, `[tool.pytest.ini_options]`,
  `[tool.coverage.report]`), `Makefile` (`cov`/`check` targets, for local
  parity with CI), a new small test module (version-consistency check),
  `openspec/specs/TESTING-TIERS.md`.
- No production code (`src/whispy/**`) changes — this is CI/test
  infrastructure only.
- CI cost/time increases: a new macOS job (single Python version, real
  model + audio synthesis attempts) and a new Linux matrix leg (3 Python
  versions) run on every push/PR; `release.yml` now runs a full CI pass on
  every tag push instead of skipping straight to the release step.
- Existing behavior for contributors: the fast default-tier job keeps its
  current pass/fail semantics (plus the new coverage floor and
  version-consistency check); the new macOS/Linux jobs are additive gates,
  not replacements.

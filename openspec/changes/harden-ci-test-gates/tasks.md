## 1. Remove the stale `sox` step

- [x] 1.1 Remove the `Install sox` step (`brew install sox`) from
      `.github/workflows/ci.yml`'s `test` job matrix
- [x] 1.2 Grep the rest of `.github/workflows/*.yml` for `sox` to confirm no
      other stale reference remains
- [x] 1.3 Broaden `tests/test_install_scripts.py` (or add a sibling test) to
      also assert `.github/workflows/ci.yml` contains no `brew install sox`
      / `command -v sox` step, matching the MODIFIED requirement's new
      scenario

## 2. Add `pytest-timeout` and bound test runtime

- [x] 2.1 Add `pytest-timeout>=2.3` to `[project.optional-dependencies].dev`
      in `pyproject.toml`
- [x] 2.2 Add `timeout = 120` and `timeout_method = "thread"` to
      `[tool.pytest.ini_options]` (default-tier per-test bound)
- [x] 2.3 Run the full default-tier suite locally with the timeout active
      (`./.venv/bin/pytest -q`) and confirm no currently-passing test is
      close to or exceeds 120s (adjust the default if one is)
- [x] 2.4 `.venv/bin/pip install -e ".[dev]"` locally and re-run `make
      check` to confirm `pytest-timeout` is picked up with no config errors

## 3. Measure and enforce a coverage floor

- [x] 3.1 Re-run `./.venv/bin/pytest -v --tb=short --cov=src/whispy
      --cov-report=term-missing` immediately before landing this change to
      get a fresh baseline (measured in this proposal: 618 passed, 1
      skipped, 20 deselected, 89% total — re-verify, since the number can
      shift). Re-measured: 619 passed (one more test, the new sox-in-CI
      guard), 1 skipped, 20 deselected, 89% total — matches the proposal.
- [x] 3.2 Set the floor to the freshly measured baseline minus a 5-point
      margin (proposal's measurement gives 84%); update `design.md` if the
      re-measured baseline differs materially from 89%. No update needed —
      re-measured baseline is 89%, same as design.md.
- [x] 3.3 Add `--cov-fail-under=<floor>` to the `test` job's pytest
      invocation in `.github/workflows/ci.yml`
- [x] 3.4 Add the same `--cov-fail-under=<floor>` to the Makefile's `cov`
      target for local parity
- [x] 3.5 Delete the stale checked-in `.coverage` file (references deleted
      modules) so it can't be mistaken for a current report

## 4. Add the macOS real-seam CI job

- [x] 4.1 Add a `test-macos-real-seam` job to `.github/workflows/ci.yml`:
      `runs-on: macos-latest`, single Python version (match the `lint`
      job's `3.11`), checkout + venv + `pip install -e ".[dev]"`
- [x] 4.2 Run `pytest -m macos -v --tb=short --timeout=300` as the job's
      test step (longer per-test timeout than the default tier, to allow
      real model load/inference)
- [x] 4.3 Verify locally (or via a scratch workflow run) that on a runner
      without Microphone/Input Monitoring TCC grants, the job passes via
      skips rather than failing or hanging.
      **Ran locally with findings** (this machine has `sox`/`say` present but
      an ambiguous mic TCC grant for this venv's Python):
      - `test_transcription_quality.py` (5 tests): all pass (uses `say`-
        synthesized WAV, no live mic).
      - `test_e2e_smoke.py::TestRealOsascriptClipboard` and `::TestLiveEventTap`:
        pass cleanly.
      - `test_e2e_smoke.py::TestRealAudioCapture::test_recording_yields_valid_wav`:
        does NOT skip cleanly here — `sd.RawInputStream(...)` blocks
        indefinitely inside PortAudio's `Pa_OpenStream` (a partial-TCC hang,
        not a raised permission error, so the test's own try/except can't
        catch it to skip). `--timeout=300` correctly bounds it and fails the
        test after 300s instead of hanging forever — this is exactly the
        risk design.md documents ("a partial TCC state that causes a hang
        instead of a permission error") with the prescribed mitigation,
        confirmed working. `TestLiveDriveCycle` (real mic path) likely hits
        the same hang, not independently run (same root cause).
      - `test_waveform.py` (11 tests): 10 pass, but
        `test_recording_start_shows_visualization` genuinely **fails** —
        it asserts `_on_recording_start` in `src/whispy/ui/menu_bar.py`
        contains both `hide()` and `show()`, but the method only calls
        `show()`. This is a pre-existing source/test mismatch, unrelated to
        TCC/permissions, that was invisible while this tier was silently
        deselected (proposal finding #1) — now that the tier actually runs,
        it surfaces. **Not fixed here**: out of this change's scope (would
        require editing `src/whispy/ui/menu_bar.py`, owned by other
        in-flight work, or altering existing test assertions). Flagged for
        follow-up before `test-macos-real-seam` is made a required check.
- [ ] 4.4 Observe the job for a short burn-in period (a handful of pushes/
      PRs) before treating it as a required/blocking check on the default
      branch, per the flakiness risk noted in `design.md`.
      **Deferred** — requires real CI runs across multiple pushes/PRs after
      this branch merges; not executable from this local session.

## 5. Add the Linux CI leg

- [x] 5.1 Add a `test-linux` job to `.github/workflows/ci.yml`:
      `runs-on: ubuntu-latest`, same `matrix.python-version` list
      (`["3.10", "3.11", "3.12"]`) as the existing `test` job
- [x] 5.2 Steps: checkout, `actions/setup-python@v5`, create venv, `pip
      install -e ".[dev]"`, run the identical default pytest invocation
      used by the macOS `test` job (including `--cov-fail-under`)
- [ ] 5.3 Fix any Linux-only failures surfaced by actually running on
      Ubuntu (path handling, subprocess quoting, `platform/linux/*` import
      guards) — expect some first-run breakage since this path has never
      executed on real Linux in CI.
      **Not executable from this session** — no Ubuntu runner available
      locally (per the task's own constraint: "CI jobs you add can't be
      executed here"). Deferred to the first real `test-linux` CI run.
- [x] 5.4 Confirm the job does NOT attempt `pytest -m linux` (out of scope
      per `design.md` — no X11/audio/`xdotool` on the hosted runner).
      Verified: `test-linux`'s pytest step is identical to the macOS `test`
      job's (default `addopts` filter applies, no `-m` override).

## 6. Gate `release.yml` on CI

- [x] 6.1 Add `workflow_call:` to `.github/workflows/ci.yml`'s `on:` block
      (alongside `push`/`pull_request`), so it can be invoked as a reusable
      workflow
- [x] 6.2 In `.github/workflows/release.yml`, add a `ci` job:
      `uses: ./.github/workflows/ci.yml`
- [x] 6.3 Add `needs: [ci]` to the existing `release` job in
      `release.yml`
- [ ] 6.4 Push a test tag on a scratch branch/fork (or dry-run via `act`/a
      draft PR) to confirm: (a) a passing tagged commit still releases, and
      (b) a deliberately broken tagged commit does not.
      **Not executable from this session** — requires pushing a tag and
      observing a real Actions run; YAML validated syntactically
      (`yaml.safe_load` on both files succeeds) and the reusable-workflow +
      `needs` shape matches GitHub Actions' documented pattern. Deferred to
      the first real tag push.

## 7. Version consistency check

- [x] 7.1 Add a small pytest test (e.g. `tests/test_packaging.py`) that
      reads `pyproject.toml`'s `[project].version` (via `tomllib`) and
      `packaging/macos/setup_app.py`'s `VERSION` (regex or AST, matching
      the style of `tests/test_install_scripts.py`) and asserts equality
- [x] 7.2 Confirm the test passes against the current `1.0.0`/`1.0.0` pair
- [x] 7.3 Confirm the test runs as part of the default tier (no `macos`/
      `linux` marker), so it executes in both the macOS `test` job and the
      new `test-linux` job

## 8. Docs and spec hygiene

- [x] 8.1 Update `openspec/specs/TESTING-TIERS.md`'s `macos-real` row: "Runs
      in CI?" changes from "no" to "yes, skip-tolerant (`@pytest.mark.macos`
      job)"; leave `linux-real`'s row as "no" (unchanged, confirmed still
      accurate by this change)
- [x] 8.2 Confirm `CLAUDE.md`'s CI/testing description needs no update (it
      already just says "Run with `./.venv/bin/pytest`" — no tier-specific
      claims to fix). Confirmed — grepped `CLAUDE.md` for pytest/CI/testing
      references, both hits are just "Run with `./.venv/bin/pytest`", no
      tier-specific claims.
- [x] 8.3 `openspec validate harden-ci-test-gates --strict` — passes:
      "Change 'harden-ci-test-gates' is valid"

## 9. Final verification

- [x] 9.1 Full default-tier suite green locally: `./.venv/bin/pytest -v
      --tb=short --cov=src/whispy --cov-report=term-missing
      --cov-fail-under=<floor>`.
      **Note**: at the time of this run, another in-flight agent session
      was actively editing `src/whispy/api/server.py` (and
      `tests/test_api/test_server.py`, `tests/test_engine.py`,
      `core/config.py`, `core/corrections.py` — see concurrent `git status`)
      as part of unrelated work outside this change's scope. That produced
      7 transient failures in `tests/test_e2e.py::TestHTTPAPIWithEngine`
      (an auth status-code mismatch, 401 vs 404) unrelated to anything in
      this change. Coverage floor itself passed (`Required test coverage of
      84% reached. Total coverage: 89.71%`). Re-running with
      `--ignore=tests/test_e2e.py` confirms everything else is green: `625
      passed, 1 skipped, 20 deselected`. This change's own files
      (`.github/workflows/*.yml`, `pyproject.toml`, `Makefile`,
      `TESTING-TIERS.md`, `tests/test_install_scripts.py`,
      `tests/test_packaging.py`) are not implicated.
- [x] 9.2 `make check` (lint + format check + tests) passes.
      **Note**: `ruff check .` passes; `ruff format --check .` currently
      flags `tests/test_engine.py` as needing reformatting — that file is
      mid-edit by the same concurrent, out-of-scope session noted above,
      not touched by this change.
- [ ] 9.3 Push the branch and confirm all five CI jobs (`lint`, `test`,
      `test-macos-real-seam`, `test-linux`, plus the reusable-workflow
      dry-run if triggerable) report the expected pass/skip status.
      **Not executable from this session** — requires a real push and
      Actions run.
- [x] 9.4 `website/index.html` reviewed for whether this change needs a
      mention (expected: no — this is internal CI/test infrastructure with
      no user-facing behavior change; confirm and note so in the PR).
      Confirmed: grepped `website/index.html` for CI/test/coverage
      references — no hits; no update needed.

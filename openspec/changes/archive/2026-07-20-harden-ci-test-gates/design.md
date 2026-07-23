## Context

The CI audit (see `proposal.md`) found that `.github/workflows/ci.yml` and
`.github/workflows/release.yml` verify less than they appear to:
`pyproject.toml`'s global `addopts` silently deselects the entire
`macos`-marked real-seam tier even on the macOS runner that could partially
run it; there is no Linux runner of any kind; a removed dependency (`sox`)
is still installed on every matrix leg; releases are gated on nothing; and
coverage/hang/version drift have no automated floor. This design closes
those gaps without touching `src/whispy/**` — it is CI/test infrastructure
only.

Baseline measured locally (same command CI runs, after installing the
missing `pytest-cov`):

```
.venv/bin/pytest -v --tb=short --cov=src/whispy --cov-report=term-missing
618 passed, 1 skipped, 20 deselected
TOTAL coverage: 89%
```

The `20 deselected` is the exact count of `macos`-marked tests
(`test_e2e_smoke.py`: 4, `test_transcription_quality.py`: 5,
`test_waveform.py`: 11), confirming finding 1 precisely. `linux`-marked
tests live only in `tests/test_e2e_smoke_linux.py` (4 tests) and are already
correctly documented in `openspec/specs/TESTING-TIERS.md` as not running in
CI (`linux-real` tier) — that convention is kept as-is; what's missing for
Linux is CI execution of the *default* (mocked/unit) tier on a real Linux
interpreter, which today only ever runs under macOS-side mocking.

## Goals / Non-Goals

**Goals:**
- A green CI run on `main` is evidence that the macOS real-seam tests were
  attempted, not silently skipped by deselection — a genuine failure there
  fails the build; an expected skip (no TCC grant, no synthesis toolchain
  on the runner) does not.
- The default (mocked/unit) test tier executes on both macOS and Linux, so
  `src/whispy/platform/linux/*` and any OS-conditional logic is exercised on
  the OS it targets, not only inferred from mocks running under Darwin.
- `ci.yml` installs only dependencies the project actually has.
- A tag push cannot produce a GitHub release unless the exact tagged commit
  passes the full CI suite in that same workflow run.
- Coverage, hangs, and version drift are bounded by automated checks, not
  human review.

**Non-Goals:**
- Running the `linux`-marked real-hardware tier (`test_e2e_smoke_linux.py`)
  in hosted CI. It needs a live X11 session, a real audio input device, and
  `xdotool`; GitHub-hosted `ubuntu-latest` runners have none of these by
  default, and building a virtual-display/virtual-audio harness (Xvfb +
  ALSA loopback) is a distinct, larger effort. `linux-real` stays local-only
  per the existing `TESTING-TIERS.md` convention.
- Raising the coverage floor aggressively or chasing 100% — the floor exists
  to catch regressions, not to force new test-writing in this change.
- Changing the release *content* (still the GitHub auto-generated source
  tarball) — only gating *when* a release is allowed to be created.
- A full toolchain fix for `test_transcription_quality.py`'s `sox`
  dependency (it still needs `sox` to synthesize speech via `say`, separate
  from the removed *audio-capture* `sox` dependency). It stays
  module-level-skipped on runners without `sox`/`say`, consistent with its
  existing self-skip design.

## Decisions

### `-m macos` in a dedicated job, not an override of the default job's `addopts`
Two options: (a) add a second `pytest -m macos ...` step/job alongside the
existing default-tier job, or (b) change the existing `test` job to run
without the global `-m 'not macos and not linux'` override on macOS so
everything runs in one pass.

Chosen: (a), a separate job (`test-macos-real-seam`).
- The real-seam tier is slow (real Whisper model load + inference, `say`
  speech synthesis) and its failure mode is different (expected skips vs.
  the default tier's expected 100%-pass). Mixing them in one job means a
  single `pytest` invocation reports mixed skip/pass semantics, making the
  job's pass/fail meaning ambiguous to a reviewer glancing at the check.
- A separate job can run a single Python version (the real-seam behavior
  under test doesn't vary by CPython interpreter version the way the
  mocked/unit tier's compatibility does), keeping the added cost to one
  macOS runner-minute bucket instead of tripling it across the matrix.
- `pyproject.toml`'s `addopts` stays the single source of truth for "what
  runs by default" (locally and in CI); the new job passes `-m macos`
  explicitly rather than each job carrying a different implicit filter.

### Linux leg runs the default tier, not `-m linux`
Rejected running `-m linux` on `ubuntu-latest`: those 4 tests need a live
X11 display (`pynput` listener), a real audio input device, and `xdotool`
none of which a default GitHub-hosted Linux runner provides, and
`TESTING-TIERS.md` already documents `linux-real` as CI-excluded by design
— changing that is a separate, larger effort (Xvfb + virtual audio sink)
that isn't part of closing "no Linux runner at all."

Chosen: add `test-linux` on `ubuntu-latest`, same Python matrix
(3.10/3.11/3.12) as the macOS `test` job, running the identical default
`pytest` invocation (mocked/unit tier). This directly closes "the `linux`
tier and `src/whispy/platform/linux/*` never execute in CI" — the
mocked/unit coverage of Linux-conditional code paths (`platform/linux/`,
`platform/detect.py`, install-script branching) now runs on the OS it
targets instead of only under Darwin-side mocking.

### `sox` removed from `ci.yml`, not just from the install scripts
The existing "Install scripts do not require sox" requirement only checks
`install.sh`/`scripts/bootstrap.sh` (`tests/test_install_scripts.py`). The
same drift can recur in any workflow file with no test catching it. Rather
than add a fourth requirement for "CI doesn't install sox" as a standalone
item, this change broadens the existing requirement's scope (title and
description) to cover both install scripts and CI workflows, since it is
the same underlying fact (the audio backend is `sounddevice`/PortAudio, not
`sox`) — see the MODIFIED requirement in the spec delta. No new automated
guard is added for the workflow file itself (YAML content isn't unit-tested
today); this is called out as an accepted risk below.

### Release gating: reusable workflow (`workflow_call`) + `needs`, not `workflow_run`
Three options considered:
- **`workflow_run`**: `release.yml` triggers on `ci.yml`'s `workflow_run`
  completing. Rejected: `workflow_run` fires for a *branch's* CI run: there
  is no guarantee a `workflow_run` event exists for the exact commit a tag
  points to (a tag can be pushed on a commit that was never itself pushed
  to `main` as HEAD, e.g. a re-tag or a tag on an older commit), and
  correlating the tag's SHA to the right prior run requires extra
  bookkeeping (`github.event.workflow_run.head_sha` matching) that is easy
  to get subtly wrong and silently pass.
- **Plain `needs:` across files**: not supported by GitHub Actions — `needs`
  only orders jobs within the same workflow file.
- **Reusable workflow (`workflow_call`) + `needs`**: chosen. Add
  `workflow_call` to `ci.yml`'s `on:` (alongside `push`/`pull_request`).
  `release.yml` gets a job that does `uses: ./.github/workflows/ci.yml`,
  and the existing `release` job adds `needs: [ci]`. This runs the entire
  CI suite (lint, macOS default tier, macOS real-seam, Linux) against the
  exact tagged commit in the same workflow run that creates the release —
  no SHA correlation, no dependency on a prior run having existed. Trade-off:
  a tag push now always re-runs full CI (a few extra minutes), even if the
  commit was already fully tested on `main` moments earlier. Accepted: tag
  pushes are infrequent (release events), and re-running is strictly safer
  than trusting a possibly-stale or possibly-nonexistent prior run.

### Version-consistency check lives in the test suite, not a bespoke CI step
Chosen: a plain pytest test (alongside the existing structural guard in
`tests/test_install_scripts.py`'s spirit) that reads `pyproject.toml`'s
`[project].version` and `packaging/macos/setup_app.py`'s `VERSION` and
asserts equality. Rejected a CI-only `grep`/`diff` step: it would only ever
run in CI, whereas a test runs locally via `make test`/`pytest` too (and
already runs in both new CI jobs' default-tier invocations), matching this
repo's existing convention of encoding release-critical invariants as
structural tests rather than workflow-only shell steps.

### Coverage floor: measured baseline minus a fixed margin, not a guessed number
Measured baseline (this session, exact CI command): **89%** total on the
default tier. Chosen floor: **84%** (`--cov-fail-under=84`), a flat 5-point
margin below the measured baseline — enough to absorb normal fluctuation
(a few lines added/removed, a branch not yet hit in a given PR) without
being loose enough to miss a real regression (e.g., a whole new module
landing with no tests, which would drop coverage by several points at
once). The exact number is re-verified in `tasks.md` immediately before
landing, since the baseline can shift between this proposal and
implementation (new tests, `pytest-cov` version differences in how partial
branches are counted).

### `pytest-timeout` default: per-test, not job-level only
GitHub Actions already has a job `timeout-minutes` safety net, but it fires
too late (the whole job, all matrix legs' worth of setup) and gives no
signal about *which* test hung. Chosen: add `pytest-timeout` to `[dev]` and
set a default per-test timeout via `[tool.pytest.ini_options]`
(`timeout = 120`, `timeout_method = "thread"`), long enough for the
slowest current mocked/unit test with margin, short enough that a hang
fails in about two minutes instead of hours. The real-seam job
(`test-macos-real-seam`), which legitimately needs longer for model
load/inference, overrides with a per-invocation `--timeout=300` rather than
raising the global default.

## Risks / Trade-offs

- **[Risk]** The macOS real-seam job may be flaky on hosted runners in ways
  that aren't a clean `pytest.skip` (e.g., a partial TCC state that causes a
  hang instead of a permission error, or a transient model-download
  failure). → **Mitigation**: `--timeout=300` on that job bounds any hang;
  the job is added and observed for a burn-in period before being treated as
  a required/blocking check (tracked in `tasks.md`).
- **[Risk]** Added CI cost/time: one more macOS job plus a 3-version Linux
  matrix on every push/PR, and a full CI re-run on every tag push. →
  **Mitigation**: the macOS real-seam job pins a single Python version
  instead of the full matrix; this is accepted cost for closing a HIGH-severity
  silent-gap finding.
- **[Risk]** No automated guard stops `ci.yml` (or any future workflow file)
  from re-introducing a `sox`/other-stale-dependency install step, since
  workflow YAML isn't unit-tested. → **Mitigation**: documented as an
  accepted gap in this change; a future change could add a lightweight
  workflow-YAML lint/grep test if this recurs.
- **[Trade-off]** The coverage floor (84%) is a flat baseline-minus-margin,
  not a ratchet that rises over time — it will not force coverage upward,
  only catch a sharp regression. Revisiting the floor periodically is a
  process follow-up, not part of this change.
- **[Trade-off]** Gating release on a full CI re-run means a maintainer
  cannot force a release past a flaky/red check without either fixing it or
  temporarily bypassing branch protection — this is the intended effect
  (finding 4 was exactly the absence of this friction) but is worth naming
  as a deliberate behavior change for whoever cuts the next release.

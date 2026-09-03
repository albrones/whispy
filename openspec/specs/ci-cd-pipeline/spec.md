# ci-cd-pipeline Specification

## Purpose
TBD - created by archiving change add-vercel-deploy-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Install scripts do not require sox

The install scripts (`install.sh`, `bootstrap.sh`) and the CI workflow (`.github/workflows/ci.yml`) SHALL NOT require or gate on `sox`, since the audio backend uses sounddevice/PortAudio.

#### Scenario: Clean machine without sox

- **WHEN** the one-liner installer runs on a machine that does not have
  `sox`
- **THEN** it SHALL proceed and complete the install (no sox check, no
  abort)

#### Scenario: CI test job does not install sox

- **WHEN** the `test` job (or any other job) in `.github/workflows/ci.yml`
  runs
- **THEN** it SHALL NOT contain a `brew install sox` (or equivalent
  package-manager) step

### Requirement: One-liner install succeeds under curl | bash
The bootstrap installer SHALL complete successfully when piped from `curl` (a non-interactive, non-TTY shell), without a prompt that defaults to aborting.

#### Scenario: Non-interactive install
- **WHEN** `bootstrap.sh` runs via `curl … | bash` with no controlling TTY
- **THEN** it SHALL NOT block on or abort due to an unanswered prompt

### Requirement: Website deployment via Vercel Git integration
The system SHALL deploy the `website/` directory to Vercel using Vercel's native Git integration connected to the repository, rather than a GitHub Actions workflow, with configuration versioned in the repository's root `vercel.json` (`framework: null`, no build command, `outputDirectory: website`) and `.vercelignore`.

#### Scenario: Production deploy on push to main
- **WHEN** a commit is pushed to the `main` branch
- **THEN** Vercel's Git integration SHALL build and deploy the site defined by `vercel.json` as a production deployment, with no GitHub Actions workflow involved

#### Scenario: Preview deploy on pull request
- **WHEN** a pull request is opened or updated against any branch
- **THEN** Vercel's Git integration SHALL create a preview deployment for that pull request

#### Scenario: No GitHub secrets required
- **WHEN** a maintainer sets up or audits the website deploy path
- **THEN** no GitHub repository secrets SHALL be required, since Vercel's Git integration authenticates and builds independently of the repository's CI

#### Scenario: Manual deploy fallback
- **WHEN** a maintainer needs to deploy outside the normal push/PR flow
- **THEN** project documentation SHALL describe running `npx vercel deploy --prod` from a checkout linked to the Vercel project via `.vercel/`

### Requirement: macOS real-seam tests execute in CI
The macOS real-seam tier SHALL run against the real transcription model in CI, loading `nemo-parakeet-tdt-0.6b-v3` int8 through `onnx-asr` on `CPUExecutionProvider`. The job SHALL allow enough wall-clock for the first-run model download (639 MB) and SHALL override the default per-test timeout for real model load and inference.

#### Scenario: Real model tier runs with an adequate timeout
- **WHEN** the macOS real-seam job executes
- **THEN** it SHALL run the `macos`-marked tests with a timeout longer than the default, covering model download, load, and inference

#### Scenario: No Whisper model is fetched in CI
- **WHEN** the CI workflows are inspected
- **THEN** no job SHALL download or cache a faster-whisper model

### Requirement: Default test tier executes on Linux in CI

CI SHALL run the default (mocked/unit) test tier on a Linux runner, in addition to macOS, so that Linux-conditional code (`src/whispy/platform/linux/*`, OS-detection branches) is exercised on the operating system it targets rather than only under macOS-side mocking.

#### Scenario: Linux job runs the default tier across the supported Python matrix

- **WHEN** the CI workflow runs on a push or pull request
- **THEN** a job SHALL run on an `ubuntu-latest` (or equivalent) runner,
  across the same supported Python versions as the macOS default-tier job,
  invoking the same default `pytest` command (no `-m macos`/`-m linux`
  override)

#### Scenario: Linux real-hardware tier remains local-only

- **WHEN** the CI workflow runs
- **THEN** it SHALL NOT attempt to run the `linux`-marked real-hardware
  tests (`tests/test_e2e_smoke_linux.py`), since hosted Linux runners lack
  a live X11 session, a real audio input device, and `xdotool` — that tier
  stays local-only, per `openspec/specs/TESTING-TIERS.md`'s `linux-real`
  definition

### Requirement: Release creation is gated on CI passing

The release workflow (`.github/workflows/release.yml`) SHALL NOT create a GitHub release for a pushed tag unless the full CI suite (lint + all test jobs) passes for that exact tagged commit, verified within the same workflow run.

#### Scenario: Tag push runs the full CI suite before releasing

- **WHEN** a `v*` tag is pushed
- **THEN** the release workflow SHALL execute the CI workflow's jobs
  (lint and all test jobs) against the tagged commit before the release
  job runs, via a reusable-workflow (`workflow_call`) invocation with a
  `needs` dependency

#### Scenario: A failing CI job blocks the release

- **WHEN** any job invoked by the release workflow's CI gate fails
- **THEN** the `release` job SHALL NOT run, and no GitHub release SHALL be
  created for that tag

### Requirement: Coverage has an enforced floor

The CI test invocation SHALL enforce a minimum coverage percentage (`--cov-fail-under`) on the default test tier, so a coverage regression fails the job instead of merging silently.

#### Scenario: Coverage drops below the floor

- **WHEN** the default-tier test run's total coverage (as measured by
  `pytest-cov`) falls below the configured floor
- **THEN** the job SHALL fail

#### Scenario: Coverage at or above the floor passes

- **WHEN** the default-tier test run's total coverage is at or above the
  configured floor
- **THEN** the coverage check SHALL NOT fail the job on that basis

### Requirement: Individual tests are bounded by a timeout

The test suite SHALL enforce a default per-test timeout so that a hung test fails with a clear timeout error instead of blocking the job indefinitely.

#### Scenario: A test exceeds the default timeout

- **WHEN** a test in the default (mocked/unit) tier runs longer than the
  configured default timeout
- **THEN** `pytest-timeout` SHALL fail that test with a timeout error,
  rather than the job hanging until the GitHub Actions job-level timeout

#### Scenario: Real-seam tests use a longer timeout

- **WHEN** a `macos`-marked test performs real model load/inference or
  real audio capture
- **THEN** its effective timeout SHALL be longer than the default-tier
  timeout, to accommodate real, non-mocked latency, while still bounding
  the maximum run time of a single test

### Requirement: Shipped version stays consistent across the codebase

The version declared in `pyproject.toml`'s `[project].version` SHALL match the version declared in `packaging/macos/setup_app.py`'s `VERSION`. A mismatch SHALL be caught automatically before release.

#### Scenario: Versions match

- **WHEN** the version-consistency test runs
- **THEN** it SHALL pass if `pyproject.toml`'s `[project].version` equals
  `packaging/macos/setup_app.py`'s `VERSION`

#### Scenario: Versions diverge

- **WHEN** `pyproject.toml`'s `[project].version` and
  `packaging/macos/setup_app.py`'s `VERSION` differ
- **THEN** the version-consistency test SHALL fail, and since it runs as
  part of the default test tier, it SHALL fail CI on every push/PR where
  the mismatch exists — not only at release time

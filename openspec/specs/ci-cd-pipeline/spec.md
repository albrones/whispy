# ci-cd-pipeline Specification

## Purpose
TBD - created by archiving change add-vercel-deploy-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Website deployment workflow
The system SHALL provide a GitHub Actions workflow that deploys the `website/` directory to Vercel. The workflow SHALL produce a Vercel preview deployment for pull requests and a Vercel production deployment for pushes to the default branch.

#### Scenario: Production deploy on main
- **WHEN** a commit that modifies files under `website/` is pushed to the `main` branch
- **THEN** the workflow SHALL build the website and deploy it to Vercel as a production deployment

#### Scenario: Preview deploy on pull request
- **WHEN** a pull request modifies files under `website/`
- **THEN** the workflow SHALL build the website and create a Vercel preview deployment (not promoted to production)

### Requirement: Path-filtered deployment triggers
The website deployment workflow SHALL only run when files under `website/` change, so that app-only commits and version-tag pushes never trigger a website deploy.

#### Scenario: App-only commit does not deploy website
- **WHEN** a commit changes only files outside `website/` (e.g. `src/`)
- **THEN** the website deployment workflow SHALL NOT run

#### Scenario: Version tag push does not deploy website
- **WHEN** a `v*` version tag is pushed
- **THEN** the website deployment workflow SHALL NOT run (only the release workflow runs)

### Requirement: Pre-deploy website validation
The system SHALL validate the website before deploying so that a broken page is caught at pull-request time rather than after it reaches production.

#### Scenario: Validation runs before deploy
- **WHEN** the website deployment workflow runs
- **THEN** a validation step SHALL verify that `website/index.html` exists and references its required local assets before any deploy step executes

#### Scenario: Validation failure blocks deploy
- **WHEN** the validation step fails
- **THEN** the workflow SHALL fail and SHALL NOT perform a Vercel deployment

### Requirement: Deployment secret configuration
The website deployment workflow SHALL authenticate to Vercel using repository secrets, and these required secrets SHALL be documented.

#### Scenario: Required secrets are referenced
- **WHEN** the workflow authenticates to Vercel
- **THEN** it SHALL read the `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` repository secrets

#### Scenario: Secrets are documented
- **WHEN** a maintainer needs to enable the deployment
- **THEN** project documentation SHALL list the `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` secrets and how to obtain them

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


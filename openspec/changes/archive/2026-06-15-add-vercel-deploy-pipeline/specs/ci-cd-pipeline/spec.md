## ADDED Requirements

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

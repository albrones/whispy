# ci-cd-pipeline Specification

## Purpose
TBD - created by archiving change add-vercel-deploy-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Install scripts do not require sox
The install scripts (`install.sh`, `bootstrap.sh`) SHALL NOT require or gate on `sox`, since the audio backend uses sounddevice/PortAudio.

#### Scenario: Clean machine without sox
- **WHEN** the one-liner installer runs on a machine that does not have `sox`
- **THEN** it SHALL proceed and complete the install (no sox check, no abort)

### Requirement: One-liner install succeeds under curl | bash
The bootstrap installer SHALL complete successfully when piped from `curl` (a non-interactive, non-TTY shell), without a prompt that defaults to aborting.

#### Scenario: Non-interactive install
- **WHEN** `bootstrap.sh` runs via `curl … | bash` with no controlling TTY
- **THEN** it SHALL NOT block on or abort due to an unanswered prompt

### Requirement: Chosen Whisper model takes effect
When the user sets `WHISPER_MODEL`, the installed daemon SHALL use that model rather than silently falling back to the default.

#### Scenario: WHISPER_MODEL=medium
- **WHEN** the user installs with `WHISPER_MODEL=medium`
- **THEN** the daemon SHALL load the `medium` model (the value SHALL be persisted to config or read at load), not the default `small`

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


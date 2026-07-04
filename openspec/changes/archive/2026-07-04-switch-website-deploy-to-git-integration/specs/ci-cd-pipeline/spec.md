## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Website deployment workflow
**Reason**: The GitHub Actions workflow (`deploy-website.yml`) that drove this requirement is deleted. It never actually worked in production — `VERCEL_TOKEN` was never provisioned as a repository secret, so every run failed at `vercel pull`. The repository is now connected to the Vercel project via native Git integration, which deploys the site directly without any Actions workflow.
**Migration**: No action needed for users; maintainers should delete the now-unused `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` repository secrets. See the new `Website deployment via Vercel Git integration` requirement for the current mechanism.

### Requirement: Path-filtered deployment triggers
**Reason**: Path filtering was a property of the deleted GitHub Actions workflow. Vercel's Git integration has no equivalent path-filter setting for this project — it deploys on every push and pull request. For a static, build-free site (`buildCommand: ""`) this is cheap and acceptable; an app-only commit still triggers a fast no-op deploy rather than being skipped.
**Migration**: None. If path filtering becomes necessary again, it would need to be configured through Vercel's project settings or a reintroduced Actions workflow, not this spec's prior mechanism.

### Requirement: Pre-deploy website validation
**Reason**: The validation step being described ran inside the deleted `deploy-website.yml` workflow, immediately before its deploy steps. Vercel's Git integration has no equivalent pre-deploy hook in this repository. The underlying invariant (the entry page and its core local assets exist) continues to be guarded independently by `tests/test_website.py`, which runs in `ci.yml` on every push and pull request.
**Migration**: None. Rely on `tests/test_website.py` / `ci.yml` for this invariant going forward.

### Requirement: Deployment secret configuration
**Reason**: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` were only needed to authenticate the deleted GitHub Actions workflow to Vercel's CLI. Vercel's Git integration authenticates independently of GitHub Actions and repository secrets.
**Migration**: Delete the `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` repository secrets (`VERCEL_TOKEN` was never set). No replacement secrets are needed.

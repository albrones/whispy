## Why

The `ci-cd-pipeline` spec requires a GitHub Actions workflow
(`deploy-website.yml`) that drives Vercel deploys via the CLI (`vercel pull`
/ `vercel build` / `vercel deploy --prebuilt`), authenticated with
`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`. In practice that
workflow never worked: `VERCEL_TOKEN` was never provisioned as a repository
secret, so every run failed at the `vercel pull` step (`--token=""`), as
recorded in the pre-v1 review session log. The org/project ids were set but
useless without the token.

Separately, the `albrones/whispy` repository has now been connected to the
Vercel project `whispy` via Vercel's native Git integration. Vercel now
builds and deploys the site directly from the repo on every push and pull
request — no token, no workflow run, no manual secret provisioning. Keeping
`deploy-website.yml` around after this means **two** deploy mechanisms exist
for the same site: one that works (Git integration) and one that has never
worked and duplicates it (Actions + CLI). The dead workflow is also
structurally guarded by `tests/test_deploy_workflow.py`, so it reads as
supported infrastructure when it isn't.

This change removes the redundant Actions pipeline and its test, updates
`docs/deployment.md` to describe the Git-integration model, and brings the
`ci-cd-pipeline` spec back in line with what actually deploys the website.

## What Changes

- Delete `.github/workflows/deploy-website.yml` — Vercel's Git integration
  replaces it entirely.
- Delete `tests/test_deploy_workflow.py` — it structurally asserted the
  now-deleted workflow's shape (path filters, secrets referenced); with the
  workflow gone it has no subject.
- Rewrite `docs/deployment.md`: website deploys are driven by Vercel's Git
  integration (push to `main` → production, pull request → preview),
  configured entirely by the committed `vercel.json`
  (`framework: null`, no build command, `outputDirectory: website`) and
  `.vercelignore`. No GitHub secrets are required for this path; the
  now-unused `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` repository secrets can be
  deleted. A manual fallback (`npx vercel deploy --prod`) is documented for
  local/debug use.
- Update `docs/SPECIFICATION.md`'s test-file inventory to drop the deleted
  `test_deploy_workflow.py`.
- **Spec**: remove the `Website deployment workflow` and `Path-filtered
  deployment triggers` requirements from `ci-cd-pipeline` (they describe the
  deleted Actions workflow) and add a new `Website deployment via Vercel Git
  integration` requirement describing the current mechanism. The
  `Pre-deploy website validation` and `Deployment secret configuration`
  requirements are also removed since both were properties of the deleted
  workflow (validation step, `VERCEL_TOKEN`/`VERCEL_ORG_ID`/
  `VERCEL_PROJECT_ID` secrets) with no equivalent in Git-integration deploys;
  `tests/test_website.py` continues to guard the site's own asset integrity
  independent of how it's deployed.

## Capabilities

### Modified Capabilities
- `ci-cd-pipeline`: website deployment SHALL be handled by Vercel's Git
  integration, configured via the versioned `vercel.json` /
  `.vercelignore`, instead of a GitHub Actions workflow; path-filtered
  triggers, the pre-deploy validation step, and the Actions-secret
  requirements are dropped since Git-integration deploys have no
  equivalent step to gate or secrets to reference.

## Impact

- `.github/workflows/deploy-website.yml` — deleted.
- `tests/test_deploy_workflow.py` — deleted.
- `docs/deployment.md` — rewritten for the Git-integration deploy model.
- `docs/SPECIFICATION.md` — test-file inventory updated.
- `openspec/specs/ci-cd-pipeline/spec.md` — requirements updated on
  archive.
- No application code, install scripts, or runtime behavior changes; the
  website's own content and `vercel.json` / `.vercelignore` are unchanged.

## Context

The website is a static, build-free site under `website/` (`index.html`, `script.js`, `styles.css`, `assets/`) plus a `vercel.json`. CI (`ci.yml`) lints/tests the Python app; the release pipeline (`release.yml`) fires only on `v*` tags and bumps the Homebrew formula. Neither touches the website. Today the website reaches production only if someone runs `vercel` by hand or relies on Vercel's Git integration — there is no workflow in-repo, so the behavior is neither reviewable nor testable.

## Goals / Non-Goals

**Goals:**
- One in-repo workflow that deploys `website/` to Vercel: preview on PR, production on `main`.
- Path-filter to `website/**` so app commits and tag pushes never deploy the site.
- Validate the site before deploying so a broken page fails the PR.
- Document the required secrets.

**Non-Goals:**
- Changing the website content or its build-free nature.
- Touching `ci.yml` or `release.yml`.
- Adding a Node build step / framework — the site is plain static files.

## Decisions

### Deploy via the official Vercel CLI
Use `vercel pull` / `vercel build` / `vercel deploy --prebuilt` driven by `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`. The CLI is the documented, stable path and works for a static project without extra config.

- PR: `vercel deploy --prebuilt` (no `--prod`) → preview URL.
- `main`: `vercel deploy --prebuilt --prod` → production.

Alternative considered: a third-party `amondnet/vercel-action`. Rejected to avoid pinning to a community action for something the official CLI does in three lines.

### Path filtering
Both triggers use `paths: ["website/**"]`. The `release.yml` comment already establishes the convention that website changes and app/tag changes are disjoint; this enforces the other direction (website pipeline ignores app changes). Tag pushes are not in the trigger set at all, so they never run this workflow.

### Validation before deploy
A small shell step asserts `website/index.html` exists and that the asset references it contains (e.g. `styles.css`, `script.js`) resolve to files on disk. This is intentionally dependency-free — matching the site itself — and runs as a job step gating the deploy step. The same invariants are asserted by a unit test so the guarantee is checked locally too.

### Workflow / job structure
Single workflow `deploy-website.yml`, two triggers (`pull_request` + `push` to `main`), one job. The job determines prod vs. preview from `github.ref`/event name. Concurrency group keyed on ref cancels superseded runs.

## Risks / Trade-offs

- **Secrets not set** → deploy step fails. Mitigated by documenting them and by the workflow being inert (no deploy) until secrets exist; the validation step still provides value on PRs.
- **Vercel Git integration double-deploy**: if the Vercel project also auto-deploys from Git, the site could deploy twice. Documented as a setup note: disable Vercel's Git auto-deploy or this workflow is the single source.

## Migration Plan

Add the workflow and docs; set the three secrets in repo settings. No code or content migration. Existing manual/Git-integration deploys are superseded once secrets are in place.

## Open Questions

- None blocking. Whether to also fail the validation on broken external links is deferred (non-goal for now).

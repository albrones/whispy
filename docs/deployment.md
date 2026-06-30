# Deployment

This document covers how the Whispy promotional website is deployed.

## Overview

The static site under [`website/`](../website) is deployed to Vercel by the
[`deploy-website.yml`](../.github/workflows/deploy-website.yml) GitHub Actions
workflow:

| Trigger                                   | Result                  |
| ----------------------------------------- | ----------------------- |
| Pull request changing `website/**`        | Vercel **preview** deploy |
| Push to `main` changing `website/**`      | Vercel **production** deploy |
| App-only commit (no `website/` change)    | _no deploy_             |
| `v*` version tag push                     | _no deploy_ (handled by `release.yml`) |

The workflow is path-filtered to `website/**`, so application changes and
release tags never trigger a website deploy. Before any deploy step runs, a
validation step asserts that `website/index.html` and its core local assets
exist — the same invariant covered by `tests/test_website.py`.

## Required repository secrets

Set these under **Settings → Secrets and variables → Actions** in the GitHub
repository:

| Secret              | What it is                                | How to obtain |
| ------------------- | ----------------------------------------- | ------------- |
| `VERCEL_TOKEN`      | Personal Vercel access token              | Vercel dashboard → **Account Settings → Tokens → Create** |
| `VERCEL_ORG_ID`     | Vercel team/organization id               | Run `vercel link` locally, then read `.vercel/project.json` (`orgId`) |
| `VERCEL_PROJECT_ID` | Vercel project id for the website         | Same `.vercel/project.json` (`projectId`) |

To generate the org/project ids: from the repo root run `npx vercel link`,
select (or create) the Vercel project for the website, and Vercel writes
`.vercel/project.json` containing both ids. (`.vercel/` is git-ignored — copy
the values into the GitHub secrets above; do not commit it.)

In the Vercel project settings, set the **Root Directory** to `website` so the
build picks up `website/vercel.json` and the static files.

## Avoiding double deploys

If the Vercel project also has Git integration enabled, a push could deploy
**twice** (once via Vercel's own Git hook, once via this workflow). Pick one:

- **Recommended:** disable Vercel's Git auto-deploy for this project
  (Vercel project → **Settings → Git → Ignored Build Step** / disconnect Git),
  and let `deploy-website.yml` be the single source of deploys.
- Or remove the workflow and rely solely on Vercel's Git integration.

## Related pipelines

- [`ci.yml`](../.github/workflows/ci.yml) — lint + test the Python app.
- [`release.yml`](../.github/workflows/release.yml) — on `v*` tag push, create a
  GitHub release (source tarball auto-attached).

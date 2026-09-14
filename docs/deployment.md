# Deployment

This document covers how the Whispy promotional website is deployed.

## Overview

The static site under [`website/`](../website) is deployed by **Vercel's
native Git integration**, connected directly to the `albrones/whispy`
repository (Vercel project: `whispy`). There is no GitHub Actions workflow
involved — Vercel watches the repo itself and deploys on merge to `main`:

| Trigger                    | Result                                  |
| --------------------------- | ---------------------------------------- |
| Push to `main`               | Vercel **production** deploy             |
| Pull request (any branch)   | **skipped** — no preview deployment      |

Preview deployments are disabled through `ignoreCommand` in `vercel.json`:
the command exits 0 (skip the build) whenever `VERCEL_ENV` is not
`production`. Vercel still registers a "Canceled" deployment for each
branch push, but nothing is built or aliased.

Because the site has no build step (see below), every push to `main`
deploys, not just ones touching `website/**` — there is no path filter. For a
static, build-free site this is cheap and acceptable; it also means an
app-only merge still triggers a (no-op, near-instant) deploy.

## Configuration

All configuration is versioned in the repo root, so it travels with the code
instead of living in unversioned Vercel project settings:

- **[`vercel.json`](../vercel.json)** — tells Vercel this is a static site
  with no build step, that the deployable output is the `website/`
  directory, and that only production builds should run:

  ```json
  {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "framework": null,
    "buildCommand": "",
    "outputDirectory": "website",
    "ignoreCommand": "[ \"$VERCEL_ENV\" != \"production\" ]"
  }
  ```

- **[`.vercelignore`](../.vercelignore)** — restricts what gets uploaded to
  Vercel to the site itself (`website/**` and `vercel.json`), excluding the
  Python app, `.venv`, and local env files. This matters for CLI deploys run
  from a local checkout (`vercel deploy`); a Git-integration build instead
  clones the repository directly on Vercel's side, so `.vercelignore` isn't
  what scopes those builds — `outputDirectory` in `vercel.json` is.

No GitHub repository secrets are required for this deploy path — Vercel
authenticates and builds independently once the Git integration is
connected. The `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` secrets used by the
prior Actions-based workflow are no longer needed and can be deleted from
the repository's **Settings → Secrets and variables → Actions**.

## Manual deploy fallback

If you ever need to deploy outside of the normal merge-to-`main` flow (e.g. to debug
a Vercel-specific issue locally), run from the repo root:

```bash
npx vercel deploy --prod
```

This requires the local checkout to be linked to the Vercel project first
(`npx vercel link`, which writes `.vercel/project.json` — git-ignored, never
commit it).

## Related pipelines

- [`ci.yml`](../.github/workflows/ci.yml) — lint + test the Python app.
- [`release.yml`](../.github/workflows/release.yml) — on `v*` tag push, create a
  GitHub release (source tarball auto-attached).

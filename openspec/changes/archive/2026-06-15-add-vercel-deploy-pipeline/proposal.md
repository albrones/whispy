## Why

The repo already ships CI (lint + test) and a Homebrew release pipeline, and a static promotional website lives under `website/` with a `vercel.json`. But nothing automates getting that website online: deploys are manual and there is no PR-time validation that the site still renders. We want a GitHub Actions pipeline that validates the website on pull requests and deploys it to Vercel on merge to the default branch, so the public site stays in sync with `main` without manual steps.

## What Changes

- Add a GitHub Actions workflow that deploys `website/` to Vercel.
  - On pull requests touching `website/`, build a Vercel **preview** deployment.
  - On push to `main` touching `website/`, build and promote a Vercel **production** deployment.
- Path-filter the workflow to `website/**` so app-only commits and tag pushes never trigger a website deploy (mirrors the release pipeline's "website pushes carry no tag" comment).
- Add a lightweight website validation step (static HTML/asset sanity check) that runs before deploy so a broken page is caught at PR time.
- Document the required repository secrets (`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`) for the deploy to function.

## Capabilities

### New Capabilities
- `ci-cd-pipeline`: Continuous integration and deployment automation, including the Vercel website deploy workflow (preview on PR, production on main) with path filtering and required-secret documentation.

### Modified Capabilities
<!-- None: existing ci.yml / release.yml behavior is unchanged. -->

## Impact

- `.github/workflows/deploy-website.yml` — new workflow (preview + production Vercel deploy, path-filtered to `website/**`).
- `website/` — deployment target; no source changes required.
- Repository secrets — requires `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.
- `docs/` — deployment/secret setup documentation.
- `tests/` — add a test asserting the website deploy workflow exists and is path-filtered correctly.

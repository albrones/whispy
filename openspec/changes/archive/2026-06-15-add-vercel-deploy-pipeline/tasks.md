## 1. Add the deploy workflow

- [x] 1.1 Create `.github/workflows/deploy-website.yml` with `pull_request` and `push` (branch `main`) triggers, both path-filtered to `website/**`
- [x] 1.2 Add a concurrency group keyed on the ref to cancel superseded runs
- [x] 1.3 Add a validation step asserting `website/index.html` exists and its referenced local assets (`styles.css`, `script.js`) resolve on disk; fail the job if not
- [x] 1.4 Add Vercel deploy steps using the official CLI (`vercel pull` / `vercel build` / `vercel deploy --prebuilt`), reading `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
- [x] 1.5 Use `--prod` only when the event is a push to `main`; otherwise produce a preview deployment

## 2. Document deployment

- [x] 2.1 Create `docs/deployment.md` describing the website deploy pipeline, the three required secrets, and how to obtain them
- [x] 2.2 Note the Vercel Git auto-deploy double-deploy caveat and how to avoid it

## 3. Add unit test

- [x] 3.1 Add a test asserting `deploy-website.yml` exists, is valid YAML, is path-filtered to `website/**`, and references the three Vercel secrets

## 4. Verification

- [x] 4.1 Run the full test suite and confirm no regression
- [x] 4.2 Validate the change with `openspec validate add-vercel-deploy-pipeline --strict`

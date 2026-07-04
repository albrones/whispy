## 1. Remove the redundant Actions pipeline

- [x] 1.1 Delete `.github/workflows/deploy-website.yml`
- [x] 1.2 Delete `tests/test_deploy_workflow.py`
- [x] 1.3 Grep the repo for any other reference to `deploy-website.yml` or `test_deploy_workflow` outside historical/archived material and clean it up (`docs/SPECIFICATION.md` test-file inventory)

## 2. Docs

- [x] 2.1 Rewrite `docs/deployment.md` to describe the Vercel Git-integration deploy model (push to `main` → production, PR → preview), the role of the committed `vercel.json` / `.vercelignore`, and the dropped GitHub-secrets requirement
- [x] 2.2 Document the manual deploy fallback (`npx vercel deploy --prod`, linked via `.vercel/`)
- [x] 2.3 Keep the "Related pipelines" section accurate (`ci.yml`, `release.yml` unchanged)

## 3. Spec sync

- [x] 3.1 Add a `MODIFIED`/`REMOVED` spec delta for `ci-cd-pipeline`: drop `Website deployment workflow`, `Path-filtered deployment triggers`, `Pre-deploy website validation`, and `Deployment secret configuration`; add `Website deployment via Vercel Git integration`
- [x] 3.2 `openspec validate switch-website-deploy-to-git-integration --strict`
- [x] 3.3 `openspec archive switch-website-deploy-to-git-integration -y`
- [x] 3.4 `openspec validate --all --strict`

## 4. Verification

- [x] 4.1 `./.venv/bin/pytest tests/ -q` — full suite green
- [x] 4.2 `./.venv/bin/ruff check .` clean
- [x] 4.3 `./.venv/bin/ruff format --check .` clean

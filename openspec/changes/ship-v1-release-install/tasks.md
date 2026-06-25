## 1. Remove the sox dependency (code)

- [ ] 1.1 Remove the `command -v sox` gate from `install.sh`
- [ ] 1.2 Remove the sox prompt/install from `scripts/bootstrap.sh`
- [ ] 1.3 Drop `depends_on "sox"` from `packaging/homebrew/whispy.rb`
- [ ] 1.4 Make `bootstrap.sh` safe under `curl | bash` (non-TTY): no prompt that defaults to abort

## 2. Honor WHISPER_MODEL (code)

- [ ] 2.1 Persist the chosen model so the daemon uses it (write `model_size` into `~/.config/whispy/config.json`, merging; or read `os.environ["WHISPER_MODEL"]` in config load)
- [ ] 2.2 Verify `WHISPER_MODEL=medium ./install.sh` results in the daemon loading `medium`

## 3. Reconcile the Linux install claim (code/docs)

- [ ] 3.1 Either add a `systemd --user` install branch to `install.sh`, or scope the one-liner / `./install.sh` docs to macOS and mark Linux best-effort
- [ ] 3.2 Update README so no advertised path silently no-ops on Linux

## 4. Release infrastructure (operational — do after code blockers land + `make validate` passes)

- [ ] 4.1 Merge `feat/rebrand` → `main`
- [ ] 4.2 Create public repo `albrones/homebrew-whispy` (empty; `homebrew-` prefix required)
- [ ] 4.3 Add `HOMEBREW_TAP_TOKEN` secret (fine-grained PAT, contents:write on the tap)
- [ ] 4.4 `git tag v0.1.0 && git push origin v0.1.0` from a `main` commit with the full tree
- [ ] 4.5 Confirm `release.yml` created the release, computed the real sha256, and bumped `Formula/whispy.rb` in the tap

## 5. Verify both install paths on a clean machine

- [ ] 5.1 `curl -fsSL …/main/scripts/bootstrap.sh | bash` succeeds with no sox present
- [ ] 5.2 `brew install albrones/whispy/whispy && brew services start whispy` succeeds
- [ ] 5.3 `curl http://localhost:9090/status` responds (with the new auth token)

## 6. Tests + validation

- [ ] 6.1 `test_homebrew_formula.py` asserts no sox dependency
- [ ] 6.2 Add a check that the installer persists `WHISPER_MODEL` (or that config-load reads it)
- [ ] 6.3 Run the full test suite + `make validate`; confirm green
- [ ] 6.4 `openspec validate ship-v1-release-install --strict`

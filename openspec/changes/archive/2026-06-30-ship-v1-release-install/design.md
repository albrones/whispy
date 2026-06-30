## Context

Two install paths are advertised: a `curl | bash` one-liner (`bootstrap.sh` → `install.sh`) and Homebrew (`brew install albrones/whispy/whispy` → `brew services start whispy`). Both are wired in code and docs but neither resolves today because the code is unmerged, the tap repo and tag don't exist, and the installer carries a stale sox dependency that aborts the non-interactive path. The release automation (`release.yml`) is correct and will populate the tap formula's url+sha256 once a tag is pushed — it just has never run.

## Goals / Non-Goals

**Goals:**
- `curl … | bash` succeeds on a clean Mac with no sox installed.
- `brew install albrones/whispy/whispy && brew services start whispy` works.
- `WHISPER_MODEL=medium` actually selects the medium model.
- The Linux install claim is either true or removed.

**Non-Goals:**
- Code-signing/notarization changes (entitlements + py2app are already sound).
- Changing `release.yml`'s sha256/tap-bump logic (it is correct).
- Full Linux daemon parity beyond a working install or an honest docs scope.

## Decisions

### Release ordering (operational)
1. Land the code fixes (this change + the security/bug changes) on `feat/rebrand`.
2. Merge `feat/rebrand` → `main` — unblocks the one-liner 404 immediately.
3. Create public repo `albrones/homebrew-whispy` (the `homebrew-` prefix is mandatory for `brew tap`).
4. Add `HOMEBREW_TAP_TOKEN` (fine-grained PAT scoped to the tap, contents:write).
5. `git tag v0.1.0 && git push origin v0.1.0` from a `main` commit containing the full tree → `release.yml` creates the release, computes the tarball sha256, and pushes the patched `Formula/whispy.rb` to the tap.
6. Verify `brew install albrones/whispy/whispy`.

### sox removal
sox is no longer a runtime dependency (sounddevice/PortAudio replaced it). Remove the `command -v sox` gate from `install.sh`, the sox prompt from `bootstrap.sh`, and `depends_on "sox"` from the formula. This also fixes the non-TTY abort, since the abort came from the sox prompt defaulting to "n" with no TTY.

### Model persistence
The installer reads `WHISPER_MODEL` but nothing consumes it. Make `install.sh` write `{"model_size": "<value>"}` into `~/.config/whispy/config.json` when the var is set (merging, not clobbering other keys), so the daemon's existing config-load picks it up. (Alternative: read `os.environ["WHISPER_MODEL"]` in `load_config` — decide during implementation; writing config is more discoverable for the user.)

### Linux
`install.sh` is macOS-only (LaunchAgent). For v1, the lower-risk option is to scope the one-liner and `./install.sh` instructions to macOS in the README and mark Linux as manual/best-effort; the higher-effort option is a `systemd --user` unit branch. Choose during implementation; either way the docs must not promise a path that silently no-ops.

## Risks / Trade-offs

- The tag/release step is irreversible-ish (a public release); cut it only after the code blockers land and `make validate` passes.
- Writing `config.json` from the installer must merge with any existing config, not overwrite it.

## Migration Plan

First real release is `v0.1.0`. Existing dev installs (editable `.venv`) are unaffected. Users who set `WHISPER_MODEL` before will now actually get that model after re-running the installer.

## Open Questions

- Linux: systemd unit now, or defer with honest macOS-only docs for v1? Leaning honest docs for v1 (Linux is secondary, best-effort).
- Model persistence via config-write vs. env-read — pick the more testable option.

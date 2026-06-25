## Why

**A real user cannot install Whispy today by either advertised path.** The review traced both end-to-end:

- **One-liner 404**: the README one-liner curls `…/whispy/main/scripts/bootstrap.sh`, but the entire rebrand/repackaging (src, daemon, formula, bootstrap, pyproject) lives only on `feat/rebrand`, not `main`. Both install paths fetch `main`.
- **`brew install` 404**: the tap repo `github.com/albrones/homebrew-whispy` does not exist; `brew install albrones/whispy/whispy` fails with "repository not found".
- **Formula placeholders**: `whispy.rb` pins `v0.1.0` with `sha256 "REPLACE_WITH_TARBALL_SHA256"`, and the repo has zero tags — the formula never resolves until a real release runs `release.yml` to bump it.
- **sox aborts the installer**: `install.sh` hard-exits if `sox` is missing and `bootstrap.sh`'s sox prompt auto-answers "n" under `curl | bash` (non-TTY) — yet the audio backend migrated to sounddevice/PortAudio and sox is no longer used. The advertised "no sox needed" one-liner aborts on a clean Mac.
- **`WHISPER_MODEL` is a silent no-op**: `install.sh`/`bootstrap.sh` read `WHISPER_MODEL` into a variable that is only echoed; no code consumes it, so `WHISPER_MODEL=medium` never changes the model (always config default `small`).
- **Linux install is broken**: README advertises Linux/X11 with the same `./install.sh`, but the script only writes a macOS LaunchAgent (`~/Library/LaunchAgents` + `launchctl`) and starts no daemon on Linux.

The release automation, entitlements, py2app bundle, and pyproject markers themselves are sound — the failures are unmerged code, missing infrastructure, and the sox/model/Linux gaps.

## What Changes

- **Operational (release infra)**: merge `feat/rebrand` → `main`; create the public `albrones/homebrew-whispy` tap repo; add the `HOMEBREW_TAP_TOKEN` secret (fine-grained PAT, contents:write on the tap); push a real `v0.1.0` tag from a `main` commit to drive `release.yml` (which computes the real sha256 and bumps the tap formula).
- **Installer (code)**: remove the sox dependency/gate from `install.sh`, `bootstrap.sh`, and the formula (sounddevice/PortAudio is the backend now); make `bootstrap.sh` non-TTY-safe.
- **Model selection**: have the installer persist the chosen `WHISPER_MODEL` into `~/.config/whispy/config.json` (or read the env in config load) so the advertised model picker works.
- **Linux**: either add a Linux (systemd `--user`) install path or scope `./install.sh` / the one-liner to macOS in the docs so the Linux claim is honest.

## Capabilities

### Modified Capabilities
- `ci-cd-pipeline`: the install scripts SHALL NOT require sox, SHALL succeed under `curl | bash`, and SHALL persist the chosen model so it takes effect.

### Added Capabilities
- `linux-support`: the documented Linux install path SHALL actually install and start the daemon (or the docs SHALL not advertise an install path that does not exist on Linux).

## Impact

- `install.sh`, `scripts/bootstrap.sh` — remove sox gate; non-TTY safety; persist `WHISPER_MODEL`; Linux branch or macOS-scope.
- `packaging/homebrew/whispy.rb` — drop `depends_on "sox"`.
- Operational (not files): `main` merge, tap repo, `HOMEBREW_TAP_TOKEN`, `v0.1.0` tag.
- `README.md` — reconcile Linux install claim with reality.
- `tests/test_homebrew_formula.py` — assert no sox dependency; add an install-script sox-free / model-persist check if feasible.

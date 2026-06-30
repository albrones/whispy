## Why

Whispy currently ships **three** overlapping macOS distribution channels: the `curl | bash` one-liner (→ `install.sh` → `com.whispy` LaunchAgent), a Homebrew **formula** (`brew services`), and the signed `Whispy.app` bundle. The README labels **two** of them "recommended" (one-liner *and* `.app`), which is incoherent. Worse, the LaunchAgent/Homebrew channels run a *shared* Python interpreter — the exact TCC-grant fragility (permissions break on a Python upgrade) that the `.app` rebrand was created to escape. And the channels actively conflict: a stale `com.whispy` LaunchAgent plus the new in-app login item means two daemons fight over `:9090` (a risk already documented in `add-login-item-toggle`).

We want **one** coherent install story: the signed `.app` is the sole recommended/supported macOS path, autostart is the in-app login item alone, Homebrew (the wrong tool — a *formula* for a GUI app) is dropped, and a single OS-detecting entrypoint gives users one command on both macOS and Linux.

This is the cleanup half of the decision whose feature half is `add-login-item-toggle` (which adds the macOS autostart toggle this change makes the *only* macOS autostart mechanism).

## What Changes

- **B — `.app` is the sole recommended macOS install.** The README presents one macOS path: build/install `Whispy.app`. The `install.sh` macOS branch is demoted to a **venv builder only** (the prerequisite `make app` already needs) — it SHALL NOT write or load a `com.whispy` LaunchAgent. macOS autostart is the in-app login item (`add-login-item-toggle`) alone.
- **C — drop the Homebrew formula.** Remove `packaging/homebrew/whispy.rb`, its release-pipeline wiring (`release.yml` tap bump, `HOMEBREW_TAP_TOKEN`), `docs/homebrew.md`, and the formula-structure test. A Homebrew **Cask** (the *right* tool for a GUI `.app`) is recorded as a future option, blocked on notarization — not done here.
- **Entrypoint OS-detect.** `bootstrap.sh` (the `curl | bash` target) detects the OS: **Linux** → existing venv + `systemd --user` flow, unchanged; **macOS** → venv + `make app` + install to `/Applications` + open, with a guarded fallback to printed manual steps when Xcode Command Line Tools are absent. One command in the README for both platforms.
- **Migration / uninstall.** The macOS path SHALL remove (disable + delete) any pre-existing legacy LaunchAgent so upgraders don't end up with the double-daemon `:9090` conflict — this includes the real legacy id `com.whisper-dictation` (pre-rebrand "Whisper Dictation") as well as the intermediate `com.whispy`. `install.sh --uninstall` on macOS removes the login item registration and both LaunchAgents if present (the `.app` itself is removed by deleting it from `/Applications`).

## Capabilities

### New Capabilities
- `macos-install`: the consolidated macOS distribution & autostart model — single OS-detecting entrypoint, `.app` as the sole recommended path, `install.sh` reduced to a venv builder, login-item as the only macOS autostart, and LaunchAgent migration/cleanup.

### Modified Capabilities
- `ci-cd-pipeline`: removes the two Homebrew requirements (formula release-pipeline documentation; formula-structure test).

## Impact

- **Scripts**: `install.sh` (drop macOS LaunchAgent install/load + uninstall of it that is now replaced by login-item handling; keep Linux systemd + venv); `scripts/bootstrap.sh` (OS-detect routing to the `.app` build on macOS).
- **Packaging**: delete `packaging/homebrew/whispy.rb`; remove the Homebrew tap-bump step + `HOMEBREW_TAP_TOKEN` from `.github/workflows/release.yml`; delete `docs/homebrew.md` and its formula-structure test.
- **Docs**: README install section collapses 3 blocks → 1 command + the `.app` flow; remove `brew install` instructions; note LaunchAgent removal for upgraders. Update the website if it mentions Homebrew/one-liner-LaunchAgent.
- **Dependencies**: none added; removes the Homebrew toolchain assumption.
- **Out of scope (non-goals)**: notarization / Developer ID / Gatekeeper-friendly *downloaded* `.app`; Homebrew **Cask** distribution (depends on notarization); auto-relaunch on crash on macOS (`KeepAlive` territory — login item only does start-at-login); any change to the Linux install mechanism beyond wrapping it in the shared entrypoint; Windows.

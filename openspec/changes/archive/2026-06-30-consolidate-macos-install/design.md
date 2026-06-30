## Context

Three macOS channels exist today (see `proposal.md`). Two share a system/Homebrew Python and so inherit the TCC-grant fragility the `.app` rebrand was built to escape; the README marks two paths "recommended"; and a stale `com.whispy` LaunchAgent + the new in-app login item (`add-login-item-toggle`) can run two daemons on `:9090`. This change consolidates to a single coherent story.

Key asymmetry uncovered while exploring: **the entrypoint can be unified, the artifact cannot.** macOS wants a signed `.app` (embedded Python → stable TCC identity, `SMAppService` autostart); Linux has no `.app` equivalent (venv + `systemd --user`). There is no common artifact — only a common *command*.

Second hard constraint: a **locally built** `.app` is not quarantined, so a self-signed ("Whispy Local Signing") or ad-hoc signature passes Gatekeeper. A **downloaded** `.app` gets `com.apple.quarantine` and Gatekeeper blocks it unless notarized (Apple Developer ID, $99/yr + `notarytool`). This is why the macOS entrypoint *builds locally* rather than downloading a prebuilt bundle, and why a Homebrew **Cask** (which would download) is deferred.

## Goals / Non-Goals

**Goals:**
- One coherent macOS install story: `.app` is the sole recommended/supported path.
- One command for the user on both OSes (`curl | bash` → `bootstrap.sh`), routing by `uname`.
- `install.sh` reduced to a venv builder on macOS; no `com.whispy` LaunchAgent on macOS.
- Login item (`add-login-item-toggle`) is the only macOS autostart mechanism.
- Drop the Homebrew formula and its pipeline/test/doc surface.
- Migrate upgraders off any stale LaunchAgent to kill the `:9090` double-run.

**Non-Goals:**
- Notarization / Developer ID / a Gatekeeper-clean *downloaded* `.app`.
- Homebrew **Cask** distribution (depends on notarization — recorded as future).
- macOS auto-relaunch on crash (`KeepAlive`/systemd `Restart` territory; out of login-item scope).
- Changing the Linux install mechanism beyond wrapping it in the shared entrypoint.
- Windows.

## Decisions

**1. Unify the entrypoint, accept the artifact asymmetry.**
`bootstrap.sh` branches on `uname`:
- `Linux` → existing flow unchanged (clone → `install.sh` → venv + `systemd --user` unit, X11).
- `Darwin` → clone → `install.sh` (venv only now) → `make app` → `cp -R dist/Whispy.app /Applications/` → `open`. README shows one command for both.

Rationale: the command is the UX; the produced artifact differing per OS is invisible to the user. Don't invent a fake common artifact.

**2. macOS builds locally, never downloads. Cask/notarization deferred.**
A downloaded ad-hoc/self-signed `.app` is quarantined and Gatekeeper-blocked; only notarization fixes that. Local build sidesteps quarantine for free. So the macOS entrypoint runs `make app` on the user's machine. The pure "download a ready `.app`" one-liner and the Homebrew **Cask** that would deliver it are both gated on notarization → future work, explicit non-goals here.

**3. Guard the macOS build on Xcode Command Line Tools; degrade to printed steps.**
`make app` (py2app + `codesign`) needs the CLT. `bootstrap.sh` (Darwin) checks for it (e.g. `xcode-select -p`); if absent it prints the manual `.app` commands and an actionable hint (`xcode-select --install`) rather than failing opaquely — mirroring how `install.sh` already guards on `python3`/`git`. Full-auto when the toolchain is present, semi-auto when it isn't.

**4. `install.sh` macOS branch becomes a venv builder; no LaunchAgent.**
Delete the macOS `com.whispy.plist` write + `launchctl load`. Keep: venv creation, deps, icons, `WHISPER_MODEL` → config. The Linux branch (systemd unit) is untouched — Linux genuinely needs a service manager since it has no `.app`/`SMAppService`. macOS autostart is now solely the in-app login item.

**5. Migrate upgraders off the stale LaunchAgent.**
On the macOS path (and in `--uninstall`), if `~/Library/LaunchAgents/com.whispy.plist` exists: `launchctl bootout`/`unload` + remove it. This resolves the documented double-daemon `:9090` conflict from `add-login-item-toggle` automatically instead of relying on the user reading a README note.

**6. Drop the Homebrew formula entirely (C).**
Remove `packaging/homebrew/whispy.rb`, the `release.yml` tap-bump job + `HOMEBREW_TAP_TOKEN` secret, `docs/homebrew.md`, and the formula-structure test. A formula was the wrong tool (it targets CLI/libs and runs a shared-Python service); the right tool for a GUI `.app` is a Cask, which is deferred on notarization. Net: less maintenance surface, one fewer TCC-fragile channel.

## Risks / Trade-offs

- **macOS install is no longer a pure one-liner.** Building locally needs the CLT and a few steps. Mitigation: full-auto when CLT present; clear printed steps + `xcode-select --install` hint otherwise. The pure one-liner returns only with notarization (future).
- **Existing Homebrew users.** `brew install` stops being documented. Mitigation: README/CHANGELOG note pointing them to the `.app` path; the formula simply stops being bumped. Small current user base (personal tap).
- **Upgraders with a live LaunchAgent.** Handled by decision 5 (auto bootout + delete). Residual risk if a user installed a LaunchAgent under a non-standard label — not auto-detected; acceptable.
- **Linux unchanged but now reached via a branch.** The OS-detect wrapper adds one `case "$(uname)"` — low risk; the Linux body is the same code path as today.
- **Coupling with `add-login-item-toggle`.** That change must land first (or together): it provides the *only* macOS autostart once the LaunchAgent is gone. Sequence: `add-login-item-toggle` → `consolidate-macos-install`.

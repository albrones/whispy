## 1. install.sh — demote macOS branch to venv builder

- [x] 1.1 Remove the macOS `com.whispy.plist` generation + `launchctl unload/load` from `install.sh` (keep venv, deps, icons, `WHISPER_MODEL` → config).
- [x] 1.2 Keep the Linux branch (systemd `--user` unit) untouched.
- [x] 1.3 Update `install.sh --uninstall` on macOS: remove any legacy LaunchAgents — both `~/Library/LaunchAgents/com.whisper-dictation.plist` (older) and `~/Library/LaunchAgents/com.whispy.plist` (bootout + delete each) — and unregister the login item if present; drop the now-irrelevant LaunchAgent-only messaging.

## 2. bootstrap.sh — single OS-detecting entrypoint

- [x] 2.1 Branch on `uname`: `Linux` → current clone + `install.sh` (venv + systemd) flow, unchanged.
- [x] 2.2 `Darwin` → clone + `install.sh` (venv) + `make app` + `cp -R dist/Whispy.app /Applications/` + `open`.
- [x] 2.3 Guard the macOS branch on Xcode CLT (`xcode-select -p`); if absent, print the manual `.app` commands + `xcode-select --install` hint instead of failing.
- [x] 2.4 On the macOS branch, migrate upgraders: if either `com.whisper-dictation.plist` (older) or `com.whispy.plist` exists, bootout + delete each (kill the `:9090` double-run) before launching the `.app`.

## 3. Drop Homebrew (C)

- [x] 3.1 Delete `packaging/homebrew/whispy.rb`.
- [x] 3.2 Remove the Homebrew tap-bump job + `HOMEBREW_TAP_TOKEN` usage from `.github/workflows/release.yml`.
- [x] 3.3 Delete `docs/homebrew.md` and the formula-structure test that guards it.
- [x] 3.4 Remove the `brew install`/`brew services` instructions from the README.

## 4. Docs & website

- [x] 4.1 README install section: collapse the 3 install blocks into one `curl | bash` command + the `.app` flow; mark `.app` as the single recommended macOS path; remove the second "recommended".
- [x] 4.2 README: note for upgraders that the old `com.whispy` LaunchAgent is removed automatically; macOS autostart is the in-app "Start at login" toggle.
- [x] 4.3 Update `website/index.html` if it references Homebrew or the LaunchAgent one-liner; reflect the single install + login-item story.
- [x] 4.4 CHANGELOG entry: consolidated macOS install, dropped Homebrew formula, single entrypoint.

## 5. Verify

> Automated proxies done: `bash -n` clean on `install.sh` + `bootstrap.sh`, full
> test suite 524 passed / 1 skipped, `release.yml` valid YAML, no dangling refs
> to deleted Homebrew files. 5.1–5.4 below are live end-to-end runs that need
> real macOS/Linux boxes (this dev machine is macOS-with-CLT only).

- [ ] 5.1 macOS clean machine: `curl | bash` builds + installs `Whispy.app`, opens it, no LaunchAgent created (`launchctl list | grep whispy` empty).
- [ ] 5.2 macOS upgrader (existing `com.whispy.plist`): entrypoint removes it; only the `.app` runs; `:9090` served by one daemon.
- [ ] 5.3 macOS without Xcode CLT: entrypoint prints manual steps + `xcode-select --install` hint, exits non-fatally.
- [ ] 5.4 Linux: `curl | bash` still produces venv + enabled `systemd --user` unit (unchanged behavior).

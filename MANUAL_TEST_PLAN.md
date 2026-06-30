# Manual test plan — before archiving

Two changes to validate end-to-end:
- **consolidate-macos-install** (tasks 5.1–5.4)
- **add-login-item-toggle** (remaining manual task 3.4: reboot autostart)

> **Pre-merge note.** These changes live on branch `feat/rebrand`, not `main`.
> The public one-liner (`curl … | bash`) pulls `main` and will NOT exercise the
> new code. Test by running the **branch-local** `bootstrap.sh` with
> `WHISPY_REF=feat/rebrand`, into a throwaway `WHISPY_HOME`.

---

## A. consolidate-macos-install

### 5.1 — macOS clean install (one-liner builds & installs Whispy.app)

Prereq: no `/Applications/Whispy.app`, no `com.whispy` LaunchAgent, Xcode CLT present.

```bash
# from the whispy repo checkout (feat/rebrand)
WHISPY_REF=feat/rebrand WHISPY_HOME=/tmp/whispy-test bash scripts/bootstrap.sh
```

Expect:
- Builds, then installs `/Applications/Whispy.app`, and opens it.
- **No LaunchAgent created:**
  ```bash
  launchctl list | grep whispy        # → empty
  ls ~/Library/LaunchAgents/com.whispy.plist 2>/dev/null   # → No such file
  ```
- App responds:
  ```bash
  curl -s http://localhost:9090/status   # → JSON status
  ```
- First hold-to-talk shows a **"Whispy"** mic prompt (not "python"/"Terminal").
  After allow: System Settings → Privacy & Security → Microphone shows **Whispy**.

### 5.2 — macOS upgrader (stale LaunchAgent removed)

Simulate an old install, then run the new entrypoint and confirm it cleans up.

```bash
# 1. Plant a fake legacy LaunchAgent
cat > ~/Library/LaunchAgents/com.whispy.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.whispy</string>
  <key>ProgramArguments</key><array><string>/bin/sleep</string><string>100000</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST
launchctl load ~/Library/LaunchAgents/com.whispy.plist
launchctl list | grep whispy        # → shows com.whispy (proof it was active)

# 2. Run the new entrypoint
WHISPY_REF=feat/rebrand WHISPY_HOME=/tmp/whispy-test bash scripts/bootstrap.sh
```

Expect:
- Prints "Removing legacy com.whispy LaunchAgent...".
- After:
  ```bash
  launchctl list | grep whispy        # → empty
  ls ~/Library/LaunchAgents/com.whispy.plist 2>/dev/null   # → gone
  ```
- Only ONE daemon on :9090 (the .app), no port fight:
  ```bash
  lsof -nP -iTCP:9090 -sTCP:LISTEN     # → a single process
  ```

### 5.3 — macOS without Xcode CLT (graceful degrade)

Hard to fully reproduce if your machine has CLT installed. Two options:

- **Quick logic check** (always available): confirm the guard the script uses.
  ```bash
  xcode-select -p; echo "exit=$?"      # exit=0 here means CLT present
  ```
  Read `scripts/bootstrap.sh` Darwin branch: when `xcode-select -p` fails it
  prints the manual `make app` steps + `xcode-select --install` hint and
  `exit 0` (no build). Confirm that branch by eye.

- **Real test** (only on a fresh macOS without CLT, or a VM): run the one-liner;
  expect it to print the manual steps + hint and exit non-fatally, with NO
  `dist/Whispy.app` produced.

### 5.4 — Linux (unchanged: venv + systemd unit)

On an X11 Linux box:

```bash
sudo apt install xdotool xclip libportaudio2     # Debian/Ubuntu
WHISPY_REF=feat/rebrand WHISPY_HOME=/tmp/whispy-test bash scripts/bootstrap.sh
```

Expect:
- venv created, `systemd --user` unit installed AND enabled:
  ```bash
  systemctl --user status whispy.service          # → active (running)
  systemctl --user is-enabled whispy.service      # → enabled
  curl -s http://localhost:9090/status            # → JSON status
  ```
- No macOS-isms, no errors about LaunchAgent.

---

## B. add-login-item-toggle (remaining manual: reboot autostart)

Prereq: `/Applications/Whispy.app` installed (from 5.1) and running.

```bash
# Before: confirm not yet a login item
# (run from the app's bundled python, or just use the menu)
```

Steps:
1. Open the Whispy menu → **Settings → Start at login** → toggle **ON**.
2. Verify the OS registered it:
   - System Settings → General → **Login Items** → shows **Whispy** under
     "Open at Login" (may say "requires approval" the first time — approve it).
3. **Reboot / log out + back in.**
4. After login: Whispy is running without launching it by hand:
   ```bash
   curl -s http://localhost:9090/status            # → JSON status
   pgrep -fl Whispy.app                            # → running
   ```
5. Toggle **OFF** in the menu → confirm it disappears from Login Items and does
   NOT start after the next reboot.

---

## C. fix-dual-instance-fullscreen-pill

Prereq: Whispy running (menu-bar or `.app`).

### C1 — Single instance / no port drift
1. Confirm one daemon: `pgrep -fl "Whispy\|whispy_daemon"` → exactly one.
2. Try to launch a second instance by hand (same binary/script).
3. Expect: it exits immediately; log shows
   `Another Whispy instance is already running on :9090`.
4. Confirm still exactly one process and `curl -s localhost:9090/status` works
   (no drift to 9091): `lsof -iTCP:9091 -sTCP:LISTEN` → empty.

### C2 — Restart hands off the lock (no overlap, no loss)
1. Change a setting in the menu (e.g. Trigger → Right Option, or model).
2. Menu → **Restart**.
3. After it comes back: `pgrep -fl "Whispy\|whispy_daemon"` → exactly one.
4. The changed setting is preserved (re-open the menu / check
   `~/.config/whispy/config.json`) — NOT reverted to defaults.

### C3 — Pill over full-screen apps
1. Put another app in full screen (e.g. Safari ⌃⌘F), make it frontmost.
2. Hold the push-to-talk trigger to record.
3. Expect: the waveform pill appears bottom-center **over** the full-screen app
   and is click-through (does not steal focus / exit full screen).
4. Release, then record again **without restarting** — the pill appears every
   time (the original bug only showed it after a restart).

---

## Cleanup after testing

```bash
rm -rf /tmp/whispy-test
# if you want to remove the test app:
#   turn off "Start at login" in the menu first, then:
rm -rf /Applications/Whispy.app
launchctl bootout gui/$(id -u)/com.whispy 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.whispy.plist
```

When all pass → tell me and I'll mark 5.1–5.4 (+ login-item 3.4) done, sync the
delta specs, and archive both changes.

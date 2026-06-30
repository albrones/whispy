## Why

Whispy's recommended macOS install path is the signed `Whispy.app` bundle (robust TCC permissions that survive Python upgrades). Unlike the `install.sh`/LaunchAgent path, the `.app` path has **no automated start-at-login** — the README tells users to add it to Login Items by hand, an easy step to miss. Result: after a reboot (or if the app is quit), the daemon is gone and the user must relaunch it manually. We want a one-click way to make Whispy start at login.

## What Changes

- Add a **"Start at login"** toggle to the **Settings** section of the macOS menu bar menu, mirroring the existing "Copy to clipboard" setting (a persisted, configurable option — not a one-off action).
- Persist the choice in Whispy config as `start_at_login` (bool), validated like the other settings, so it behaves consistently with model/language/copy/trigger.
- Toggling ON persists `start_at_login=true` **and** registers the running `Whispy.app` as a login item via `SMAppService.mainAppService`; OFF persists `false` **and** unregisters it.
- On startup, **reconcile the OS login-item state to the saved config** (re-register if the saved intent is ON but the OS is not enabled, e.g. after the app was rebuilt/moved). Config is the user's intent; the OS registration is the mechanism kept in sync with it.
- The toggle is shown **only when running as a `.app` bundle** (`resolve_app_bundle()` is not `None`) and on **macOS 13+** (where `SMAppService` exists). For the loose-script/`install.sh` path — which already autostarts via its LaunchAgent — the item is hidden.
- Reach `SMAppService` through `objc.loadBundle` on the already-installed `pyobjc-core`; **no new dependency**.

## Capabilities

### New Capabilities
- `login-item-autostart`: macOS-only menu control to register/unregister the running app bundle as a login item, with live OS-backed state and availability gating (bundle + macOS 13+).

### Modified Capabilities
<!-- None: trigger-selection-ui / menu-bar-theming cover other menu concerns; this adds a new, independent control. -->

## Impact

- **Code**: `src/whispy/core/config.py` (new `start_at_login` default + bool validation); `src/whispy/ui/menu_bar.py` (settings toggle + handler + startup reconciliation); new helper `src/whispy/platform/macos/login_item.py` (the `objc.loadBundle` dance: register / unregister / status / availability).
- **Dependencies**: none added (uses installed `pyobjc-core`).
- **Install/docs**: no change to `install.sh`. README Login-Items instruction (lines ~52-55) can later note the in-app toggle.
- **Operational risk**: if an old `com.whispy` LaunchAgent is still active *and* the user enables the login item, two daemons compete for `:9090`. Out of scope to auto-resolve; called out in design.

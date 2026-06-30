## Context

Whispy ships two macOS install paths (README):

- **`install.sh` / LaunchAgent path** — writes `~/Library/LaunchAgents/com.whispy.plist` with `RunAtLoad=true` + `KeepAlive=true`, so it already starts at login and relaunches on crash. TCC grant is fragile (breaks when the Python interpreter path changes).
- **Signed `Whispy.app` bundle path (recommended)** — stable signed identity, TCC grants survive Python upgrades, but **no autostart**: the README asks the user to add the app to System Settings → Login Items by hand and remove the old LaunchAgent.

The menu (rumps) is built in `src/whispy/ui/menu_bar.py`. It already has a toggle pattern (`_on_toggle_copy`, `menu_bar.py:371`) and a bundle resolver `resolve_app_bundle()` (`src/whispy/core/paths.py`, used in `_on_reload`). `pyobjc-core` is installed; the dedicated `pyobjc-framework-ServiceManagement` is not, but `objc.loadBundle('ServiceManagement', ...)` resolves `SMAppService` from the system framework (verified on this machine, macOS 26.5).

## Goals / Non-Goals

**Goals:**
- A persisted "Start at login" setting in the Settings menu, consistent with the other settings (model/language/copy/trigger).
- OS login-item registration kept in sync with the saved setting, including self-healing on startup.
- Zero new dependencies; minimal, well-contained code.

**Non-Goals:**
- Auto-relaunch on crash/quit (that is `KeepAlive`/`systemd Restart` territory, only on the LaunchAgent path — explicitly the *other* option the user did not pick).
- Any change to the `install.sh` / LaunchAgent path (it already autostarts).
- Linux/Windows autostart UI.
- Auto-detecting or removing a stale `com.whispy` LaunchAgent.

## Decisions

**1. Reach `SMAppService` via `objc.loadBundle`, not a new pyobjc framework package.**
A small helper module `src/whispy/ui/macos/login_item.py` does the load once and exposes:
- `available() -> bool` — True only if the `ServiceManagement` bundle loads and `SMAppService` is present (implicitly macOS 13+).
- `is_enabled() -> bool` — maps `SMAppService.mainAppService().status` to a bool (status enum value `1` = enabled).
- `enable() -> bool` / `disable() -> bool` — call `registerAndReturnError_(None)` / `unregisterAndReturnError_(None)`; return success.

Rationale: ponytail — reuse installed `pyobjc-core`, no dependency churn, isolate the Objective-C bridge behind a plain-Python API so `menu_bar.py` stays clean and the bridge is unit-testable/mskable.

**2. `SMAppService.mainAppService` registers the *running* bundle — so gate on bundle identity.**
The toggle is added to the menu only when `resolve_app_bundle() is not None` **and** `login_item.available()`. Under the loose-script path `mainAppService` has no meaningful bundle identity and that path already autostarts via its LaunchAgent — so hiding the toggle is correct, not a limitation.

**3. Config is the source of truth; the OS registration is kept in sync.**
Add `start_at_login: False` to `DEFAULT_CONFIG` with bool validation, exactly like `copy_to_clipboard`. The menu toggle's checked state reflects the **config** value (consistent with every other setting), not a live OS read. Rationale: the user asked for a real, persisted setting in Settings — consistency with model/language/copy/trigger matters more than mirroring transient OS state. (Earlier draft made state OS-owned/non-persisted; reversed per user request.)

**4. Handler mirrors `_on_toggle_copy`, plus OS sync.**
`_on_toggle_login_item(sender)`: `enabled = not cfg["start_at_login"]`; `engine.update_config({"start_at_login": enabled})`; call `login_item.enable()`/`disable()`; set the title from `enabled`. The OS call lives in the UI layer so `core` stays free of macOS-UI coupling.

**5. Startup reconciliation (UI layer).**
In `WhisperMenuBarApp.__init__`, when `resolve_app_bundle()` and `login_item.available()`: if `cfg["start_at_login"]` and not `login_item.is_enabled()` → `enable()`; if not `cfg["start_at_login"]` and `login_item.is_enabled()` → `disable()`. This makes the saved intent self-healing (e.g. the bundle was rebuilt/moved and lost its registration) and honors a saved opt-out. Drift from System Settings is resolved toward the app's saved intent on next launch — acceptable and simple.

## Risks / Trade-offs

- **Double-run with a stale LaunchAgent.** If a `com.whispy` LaunchAgent still exists and the user enables the login item, two daemons fight for `:9090`. Out of scope to auto-fix. Mitigation: the README already instructs removing the LaunchAgent on the `.app` path; we can add a one-line note pointing at the in-app toggle. Optional follow-up: detect the plist and warn.
- **macOS may require user approval.** First registration can land in a "requires approval" state visible under System Settings → Login Items; `register` succeeds but the item may not run until approved. Since the toggle now reflects config (intent), it shows on; reconciliation will retry `enable()` on next launch. Acceptable.
- **Config vs System Settings drift.** If the user disables the item via System Settings but config still says on, startup reconciliation re-enables it. This favors the app's saved intent; a user who wants it off should toggle it off in Whispy. Acceptable trade for consistency/simplicity.
- **Objective-C bridge fragility.** `loadBundle` and selector calls are guarded; `available()` returning False (load failure, old OS) simply hides the toggle — no crash on menu build.
- **Testability.** The `objc` bridge can't run in CI on Linux; keep `login_item.py` thin and behind `available()` so `menu_bar` logic (show/hide, title) can be tested with the helper monkeypatched.

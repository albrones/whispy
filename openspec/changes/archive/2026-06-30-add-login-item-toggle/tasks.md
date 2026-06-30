## 1. Login-item helper

- [x] 1.1 Create `src/whispy/platform/macos/login_item.py` (platform home, not `ui/macos/`) that loads `ServiceManagement` via `objc.loadBundle` once at import (guarded; failure → unavailable).
- [x] 1.2 Implement `available() -> bool` (bundle loaded + `SMAppService` present ⇒ macOS 13+).
- [x] 1.3 Implement `is_enabled() -> bool` from `SMAppService.mainAppService().status` (enabled == status value 1).
- [x] 1.4 Implement `enable() -> bool` / `disable() -> bool` via `registerAndReturnError_(None)` / `unregisterAndReturnError_(None)`; return success, swallow/ log bridge errors.

## 2. Config-backed setting

- [x] 2.0 Add `start_at_login: False` to `DEFAULT_CONFIG` in `src/whispy/core/config.py` with bool validation (mirrors `copy_to_clipboard`).

## 3. Menu integration

- [x] 3a.1 In `src/whispy/ui/menu_bar.py`, build the "Start at login" `MenuItem` in the Settings section only when `resolve_app_bundle() is not None` and `login_item.available()`.
- [x] 3a.2 Set its initial checked title from `cfg["start_at_login"]` (persisted config) using `menu_theme.toggle_title` (match "Copy to clipboard" styling).
- [x] 3a.3 Insert the item into the `self.menu` list within the Settings group (after `copy_menu`/`trigger_menu`).
- [x] 3a.4 Add `_on_toggle_login_item(sender)`: flip `cfg["start_at_login"]`, persist via `engine.update_config`, sync OS via `enable()`/`disable()`, set title from the new value.
- [x] 3a.5 Add `_reconcile_login_item(want)` and call it on init to sync OS registration to the saved setting (self-heal / honor opt-out).

## 4. Tests & docs

- [x] 4.1 Tests: toggle handler persists config + syncs OS; `_reconcile_login_item` enable/disable/noop; `_unwrap` bool/tuple; config default + bad-value validation.
- [x] 4.2 Update README Login-Items note (~lines 52-55) to mention the in-app "Start at login" toggle and the double-run caveat (remove any old `com.whispy` LaunchAgent).
- [x] 4.2b Update the marketing site (`website/index.html`): add a "Start at login" toggle row to the menu-bar demo dropdown, and mention it in the "Lives in the tray" feature card.
- [x] 4.3 Verified on built `.app` (bundled python, `com.whispy` identity): `available()=True`, `enable()` → `SMAppService.status` 1 (Enabled), `disable()` → 0 (NotRegistered). Caught + fixed a real bug: `registerAndReturnError_(None)` returns a bare bool (no BridgeSupport metadata via raw `loadBundle`), not an `(ok, err)` tuple — see `_unwrap`.
- [ ] 3.4 Remaining manual (needs reboot): enable toggle in the live menu → reboot/relogin → confirm Whispy auto-starts.

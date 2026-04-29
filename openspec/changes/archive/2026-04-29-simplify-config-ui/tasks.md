## 1. Simplify DEFAULT_CONFIG in engine.py

- [ ] 1.1 Remove `"compute_key"` and `"trigger_key"` from `DEFAULT_CONFIG`
- [ ] 1.2 Remove `COMPUTE_OPTIONS` dict (no longer needed)
- [ ] 1.3 Update `_trigger_keycode_from_config` to always return keycode 44
- [ ] 1.4 Update `start_fn_listener` to always use keycode 44
- [ ] 1.5 Update `update_config` to ignore `compute_key` and `trigger_key` updates

## 2. Simplify menu_bar.py UI

- [ ] 2.1 Remove `self._build_menu()` trigger key submenu building code
- [ ] 2.2 Remove `self._build_menu()` compute submenu building code
- [ ] 2.3 Remove `self.trigger_key_menu` and `self.compute_menu` from the menu list
- [ ] 2.4 Remove `self._on_trigger_select`, `self._on_learn_trigger` callbacks
- [ ] 2.5 Remove `self._on_compute_select` callback
- [ ] 2.6 Remove `PRESET_TRIGGERS` and `keycode_to_label` imports
- [ ] 2.7 Remove `COMPUTE_OPTIONS` import
- [ ] 2.8 Remove `self.learn_trigger_item` menu item
- [ ] 2.9 Update Language submenu to only show "fr" and "en" (remove "auto")
- [ ] 2.10 Update `fn_status_item` to always show "Trigger: Fn ✓"

## 3. Simplify event_tap.py

- [ ] 3.1 Remove `PRESET_TRIGGERS` dict
- [ ] 3.2 Remove `keycode_to_label` function
- [ ] 3.3 Simplify `EventTapListener` to always use keycode 44
- [ ] 3.4 Remove `start_learning` and `stop_learning` methods

## 4. Update API server

- [ ] 4.1 Add validation in `/config` POST to reject `trigger_key` updates
- [ ] 4.2 Add validation in `/config` POST to reject `compute_key` updates
- [ ] 4.3 Return 400 error with explanatory message for rejected keys

## 5. Add unit tests

- [ ] 5.1 Test that DEFAULT_CONFIG no longer contains `compute_key` or `trigger_key`
- [ ] 5.2 Test that `_trigger_keycode_from_config` always returns 44
- [ ] 5.3 Test that API rejects `trigger_key` config update with 400
- [ ] 5.4 Test that API rejects `compute_key` config update with 400
- [ ] 5.5 Test that Language menu only contains "fr" and "en"

## 6. Update existing tests

- [ ] 6.1 Update tests that reference `COMPUTE_OPTIONS`
- [ ] 6.2 Update tests that reference `PRESET_TRIGGERS`
- [ ] 6.3 Update tests that reference trigger key selection
- [ ] 6.4 Update tests that reference "auto" language option

## 7. Verification

- [ ] 7.1 Run full test suite
- [ ] 7.2 Verify all tests pass

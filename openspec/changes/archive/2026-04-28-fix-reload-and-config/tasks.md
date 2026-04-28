## 1. Fix restart path in menu bar

- [x] 1.1 Update `_on_reload` in `menu_bar.py` to use `whispy_daemon.py` at project root instead of `whispy.py`
- [x] 1.2 Verify the resolved path exists before launching (add a guard with user-facing alert if missing)

## 2. Fix copy_to_clipboard menu fallback default

- [x] 1.3 Change `menu_bar.py` line 144 fallback default from `True` to `False` to match `DEFAULT_CONFIG`

## 3. Add config validation in save_config

- [x] 3.1 In `engine.py` `save_config`, filter incoming config dict to only include keys from `DEFAULT_CONFIG`
- [x] 3.2 Log a warning to stderr for each unknown key that is filtered out
- [x] 3.3 Verify that `update_config` in `Engine` still works (it already filters by `DEFAULT_CONFIG` before assignment)

## 4. Add unit tests

- [x] 4.1 Create `tests/test_config_validation.py` with tests for `save_config` filtering unknown keys
- [x] 4.2 Create `tests/test_restart_path.py` with tests for the restart path resolution
- [x] 4.3 Test that valid configs pass through unchanged
- [x] 4.4 Test that mixed valid/invalid configs save only valid keys
- [x] 4.5 Test that the restart path resolves to an existing file

## 5. Verification

- [x] 5.1 Manually test the Restart menu item launches the daemon
- [x] 5.2 Verify existing config files are loaded without errors
- [x] 5.3 Verify `copy_to_clipboard` toggle default matches `DEFAULT_CONFIG`

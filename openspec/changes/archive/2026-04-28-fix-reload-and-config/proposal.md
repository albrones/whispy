## Why

The menu bar "Restart" button is completely broken due to a hardcoded path pointing to a non-existent `whispy.py` file instead of the actual entry point `whispy_daemon.py`. Additionally, the config system lacks validation, allowing invalid configurations to be saved silently. The `copy_to_clipboard` menu fallback also has an inconsistent default value. These issues undermine user trust and reliability of the application's core configuration management.

## What Changes

- Fix `_on_reload` in `menu_bar.py` to use the correct entry point `whispy_daemon.py` instead of the non-existent `whispy.py`
- Fix the `copy_to_clipboard` menu fallback default from `True` to `False` to match `DEFAULT_CONFIG`
- Add config validation in `save_config` to reject unknown/invalid keys and raise an error with a clear message
- Add unit tests for the restart flow and config validation logic

## Capabilities

### New Capabilities
- `config-validation`: Validate configuration before saving to reject unknown keys and enforce schema integrity

### Modified Capabilities
- `core-engine`: Add config validation requirement; fix default value for `copy_to_clipboard` in menu fallback

## Impact

- `src/whispy/ui/menu_bar.py`: Fix `_on_reload` path and `copy_to_clipboard` menu fallback
- `src/whispy/core/engine.py` or config module: Add `save_config` validation logic
- New test files for config validation and restart flow
- No breaking API changes; purely internal bug fixes and hardening

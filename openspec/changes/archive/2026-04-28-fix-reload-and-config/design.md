## Context

The Whispy application runs as a macOS LaunchAgent with a menu bar UI (`rumps`). The main entry point is `whispy_daemon.py` at the project root. The menu bar UI lives in `src/whispy/ui/menu_bar.py` and provides configuration controls and a "Restart" button that should relaunch the daemon.

Currently:
- `_on_reload` (line 336) constructs a path to `whispy.py` which doesn't exist — only `whispy_daemon.py` exists at the project root.
- `copy_to_clipboard` menu fallback uses `True` as default (line 144), but `DEFAULT_CONFIG` defines it as `False`.
- `save_config` in `engine.py` accepts any dict without validating keys against `DEFAULT_CONFIG`, so typos or invalid keys silently persist.

## Goals / Non-Goals

**Goals:**
- Fix the restart path to point to the correct entry point
- Align `copy_to_clipboard` menu fallback default with `DEFAULT_CONFIG`
- Add config validation to prevent saving invalid configurations
- Add tests for the restart path and config validation

**Non-Goals:**
- Refactoring the entire config system
- Adding a config migration path for existing users
- Changing the restart mechanism (still uses subprocess)
- Adding a settings UI panel

## Decisions

### 1. Restart path: resolve relative to project root

**Decision**: Use `SCRIPT_DIR` (already computed as `Path(__file__).resolve().parent.parent.parent`) to point to `whispy_daemon.py` at the project root.

**Rationale**: `SCRIPT_DIR` is already a module-level constant in `menu_bar.py`. It resolves to the project root regardless of where the app is launched from. This is more robust than hardcoding `~/Library/LaunchAgents` paths or using `sys.argv[0]`.

**Alternatives considered**:
- Use `launchctl` to unload/load the plist — more correct for LaunchAgent management but adds complexity and requires knowing the plist path.
- Use `sys.argv[0]` — fragile if the app is launched differently.

### 2. Config validation: reject unknown keys in `save_config`

**Decision**: In `save_config`, filter the incoming config dict to only include keys present in `DEFAULT_CONFIG`. Log a warning for any unknown keys and exclude them from the saved file.

**Rationale**: This is a defensive pattern that prevents silent corruption. Raising an exception would break existing code paths that pass extra keys (e.g., internal state). Filtering with a warning is the safest approach — it preserves backward compatibility while preventing data loss.

**Alternatives considered**:
- Raise `ValueError` on unknown keys — too aggressive, would break existing code.
- Strict mode flag — adds API surface without proportional benefit.

### 3. `copy_to_clipboard` fallback: use `DEFAULT_CONFIG` value

**Decision**: Change line 144 from `True` to `False` to match `DEFAULT_CONFIG["copy_to_clipboard"]`.

**Rationale**: The `cfg.get("copy_to_clipboard", True)` default should match `DEFAULT_CONFIG`. Since `load_config` already merges `DEFAULT_CONFIG` into the config dict, the key should always exist. The fallback is a safety net that should default to the same value.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| `SCRIPT_DIR` resolves incorrectly if tests run from a different working directory | Tests should set the working directory or use explicit paths |
| Filtering unknown keys in `save_config` silently drops them | Log a warning to stderr so developers notice during testing |
| Existing config files may have unknown keys from previous versions | The filter will drop them on next save — acceptable since they were already invalid |

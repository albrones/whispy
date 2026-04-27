## Why

The current default configuration uses `"auto"` language detection and `copy_to_clipboard: true`, which may not match the primary use case for Whispy (French-speaking users who want direct text injection). Setting explicit, well-chosen defaults improves the out-of-the-box experience and reduces configuration friction for new users.

## What Changes

- Change `DEFAULT_CONFIG["language"]` from `"auto"` to `"fr"` (French as default language)
- Change `DEFAULT_CONFIG["copy_to_clipboard"]` from `True` to `False` (disable clipboard copy by default)
- No changes to other defaults (`model_size: "small"`, `compute_key: "cpu-int8"`, `trigger_key: "fn"` are already correct)

## Capabilities

### Modified Capabilities
- `core-engine`: default language changes from `"auto"` to `"fr"`, default `copy_to_clipboard` changes from `True` to `False`

## Impact

- `src/whispy/core/engine.py` — update `DEFAULT_CONFIG` dict
- `openspec/specs/core-engine/spec.md` — update requirements to reflect new defaults
- Existing tests may need updates if they assert on old default values

## Context

Whispy uses `DEFAULT_CONFIG` in `src/whispy/core/engine.py` to define application defaults. The current defaults are:
- `model_size: "small"` (466 MB, recommended)
- `compute_key: "cpu-int8"` (CPU int8, optimal for Apple Silicon)
- `language: "auto"` (requires >= 1s audio for reliable detection)
- `copy_to_clipboard: True` (copies transcribed text to clipboard)
- `trigger_key: "fn"` (Function key as trigger)

## Goals / Non-Goals

**Goals:**
- Set French as the default language (primary use case)
- Disable clipboard copy by default (text injection is the primary output)
- Keep `model_size`, `compute_key`, and `trigger_key` defaults unchanged

**Non-Goals:**
- Adding new configuration options
- Changing the config persistence mechanism
- Modifying the UI menus

## Decisions

### Decision: Minimal change — only update `DEFAULT_CONFIG` values
- **Why:** This is a configuration-only change. No new architecture or behavior changes.
- **Alternatives considered:**
  - Add a "first-run setup wizard" → overkill, adds UI complexity
  - Detect system language automatically → adds dependency, unreliable

### Decision: Keep French as hardcoded default
- **Why:** Simplifies the common case for French-speaking users. Users can still change it via UI.
- **Alternatives considered:**
  - Detect macOS system language → adds complexity, may not match user preference

## Risks / Trade-offs

[Risk] Non-French speaking users lose auto-detect out of the box
→ Mitigation The UI still allows language selection; users can switch to "Auto-detect" or "English".

[Risk] Existing users with `copy_to_clipboard: true` in their config won't see changes
→ Mitigation Config is persisted per-user; only new installations get the new defaults.

## Why

The menu bar UI exposes configuration options (trigger key, compute backend, language=auto) that are either non-essential or don't work reliably. This creates unnecessary complexity for the average user. Simplifying the UI by removing these options reduces confusion and maintenance burden while keeping the core functionality intact.

## What Changes

- Remove the "Trigger Key" submenu from the menu bar (always use "fn" as the trigger key)
- Remove the "Compute" submenu from the menu bar (always use "cpu-int8" as the compute backend)
- Remove the "auto" option from the Language submenu (keep only "fr" and "en")
- Remove the "Learn trigger key" menu item
- Clean up related callbacks and state management code
- **BREAKING**: Users can no longer change the trigger key or compute backend from the UI

## Capabilities

### Modified Capabilities
- `event-listener`: trigger key is always "fn" (keycode 44), no longer configurable via UI
- `api-interface`: remove trigger_key and compute_key from config API
- `core-engine`: remove trigger_key and compute_key from DEFAULT_CONFIG; always use "fn" and "cpu-int8"

## Impact

- `src/whispy/ui/menu_bar.py` — remove trigger_key_menu, compute_menu, learn_trigger_item; simplify menu structure
- `src/whispy/core/engine.py` — remove COMPUTE_OPTIONS, simplify DEFAULT_CONFIG
- `src/whispy/hardware/event_tap.py` — remove PRESET_TRIGGERS, simplify EventTapListener
- `src/whispy/api/server.py` — remove trigger_key and compute_key from config endpoints
- `tests/` — update tests that reference trigger key selection or compute options

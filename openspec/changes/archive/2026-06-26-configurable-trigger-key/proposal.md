## Why

Today the push-to-talk trigger is hard-wired to Fn in the user's mind: the menu shows a dead "Hold Fn to dictate" label and offers no way to change it. Some users can't use Fn comfortably (external keyboards without a Globe/Fn key, Fn remapped by the OS, accessibility) and want a different hold key. The core already accepts a configurable trigger — the only missing piece is exposing the choice.

## What Changes

- Replace the static "Hold Fn to dictate" menu label with a live **Trigger** submenu (mirroring the existing Model/Language submenus), letting the user pick the push-to-talk key from a curated preset list with a checkmark on the current choice.
- Curated presets only (Fn default, Right Command, Right Option, F13, Caps Lock) — keys that work as hold-to-talk without blocking normal typing or stealing system keys. Arbitrary "press any key" capture is explicitly out of scope.
- Make the trigger change apply **live**: selecting a trigger restarts the key listener immediately, instead of requiring a "Restart". The selected trigger persists to config (`trigger` key, already supported).
- The submenu title reflects the active trigger ("Trigger: Fn"), consistent with "Model: …" / "Language: …".

## Capabilities

### New Capabilities
- `trigger-selection-ui`: Menu-bar UI for choosing the push-to-talk trigger key from a curated preset list, showing the current selection and persisting the choice.

### Modified Capabilities
- `core-engine`: Config update for the `trigger` key SHALL restart the key listener so a trigger change takes effect immediately (currently only `model_size` / streaming params react to `update_config`).

## Impact

- `src/whispy/ui/menu_bar.py`: replace `fn_status_item` with a `Trigger` submenu + select callback + title updater (new `_on_trigger_select`, `_update_trigger_title`); register in `_refresh_accents` for theming.
- `src/whispy/core/engine.py`: `update_config` restarts the Fn listener when `trigger` changes (`stop_fn_listener()` + `start_fn_listener()`), guarded so it only runs when the listener is active.
- `src/whispy/core/config.py`: define the curated trigger preset list (name → keycode) for the UI to consume; reuses existing `trigger` validation.
- No change to `event-listener` (already decodes configurable triggers) or the `trigger` config schema.
- No new dependencies.

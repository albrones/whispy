## Why

The two `Control+Option+Command` combination presets (`⌃⌥⌘E`, `⌃⌥⌘F`) were added
by `add-toggle-dictation-mode` as a foundation for a per-trigger language
feature that never shipped and is now abandoned: the ASR backend cannot be
forced to a language (`onnx-asr` reads `language` only on its Canary path, never
on the Parakeet TDT path Whispy uses). Without that feature the combos are two
four-finger chords with no advantage over the inert single keys already offered,
and they double the Trigger submenu for nothing. Remove them.

## What Changes

- Remove `⌃⌥⌘E` and `⌃⌥⌘F` from the curated trigger presets. The Trigger
  submenu offers the inert single keys only: Fn, Right Command, Right Option,
  F13.
- The website's trigger list drops the two chords.
- The modifier-combination decode path (`parse_trigger`, mask matching on
  macOS, modifier tracking on Linux) is **kept**. A hand-edited
  `"trigger": "ctrl+alt+cmd+e"` in `config.json` keeps working and still
  renders as itself in the submenu title. Removing the decoder is a separate,
  larger deletion and is out of scope here.
- No config migration: the presets were menu labels over string values, and a
  persisted combination string remains valid.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities

- `trigger-selection-ui`: the curated preset set no longer includes
  modifier-combination presets. The requirement that combinations be labelled
  by their keys (not a language) becomes moot for the menu and is dropped; the
  "hand-edited combination renders as itself" scenario stays because the
  decoder stays.

## Impact

- **Code**: `src/whispy/core/config.py` (`TRIGGER_PRESETS`, header comment),
  `tests/test_menu_bar.py` (the combo-select test moves to a single-key preset),
  `tests/test_config_validation.py` (preset-shape assertions still pass;
  string-valued presets simply no longer occur).
- **Website**: `website/index.html` trigger list (project rule: same change).
- **Untouched**: `hardware/event_decode.py`, `hardware/event_tap.py`,
  `platform/linux/hotkey.py` and their tests.
- **Archive ordering**: this delta MODIFIES the same `Trigger selection submenu`
  requirement that `add-toggle-dictation-mode` MODIFIES. That change must be
  archived first so this delta lands on top of it, not under it.

## Context

The push-to-talk trigger is already configurable at the core: `config["trigger"]` accepts `None` (platform default), an int macOS keycode, or a string key name (`config.py:54`, validated `config.py:156`). `engine.resolve_trigger()` (`engine.py:592`) feeds it to `EventTapListener(trigger_keycode=…)`, and `decode_trigger_event` (`event_decode.py:138`) already handles three cases: the Fn secondary-flag convention (keycode 63), generic modifiers via flag-bit transition (so a held modifier emits a real release, not a perpetual press), and regular key_down/key_up.

What's missing is purely surface:
1. **No UI** — `menu_bar.py:135` is a dead disabled label `"Hold Fn to dictate"`.
2. **No live-apply** — `update_config` (`engine.py:700`) reacts to `model_size` and streaming params, but not `trigger`; a trigger change wouldn't take effect until Restart.

This change adds the menu submenu and the listener restart. It deliberately mirrors the existing Model/Language submenu pattern (`menu_bar.py:102-124`) rather than inventing new UI.

## Goals / Non-Goals

**Goals:**
- Let the user choose the push-to-talk trigger from the menu, from a curated set of keys that work well as hold-to-talk.
- Persist the choice and apply it immediately (no Restart).
- Reuse the existing config schema, decode logic, and submenu/theming patterns.

**Non-Goals:**
- "Press any key to bind" capture mode (option B). Out of scope; the curated list covers the realistic cases and avoids binding to keys that break typing or steal system shortcuts.
- Multi-key combos / chords.
- Linux trigger UI (Linux has no rumps menu bar; its trigger stays config-file driven).
- Validating that the chosen key is physically present on the user's keyboard.

## Decisions

**Curated preset list, not free capture.** Define the presets in `config.py` as an ordered name→trigger mapping the UI consumes:

```
TRIGGER_PRESETS = [
    ("Fn",            None),   # platform default (Fn / keycode 63 on macOS)
    ("Right Command", 54),
    ("Right Option",  61),     # see note below — verify keycode at build time
    ("F13",           105),
    ("Caps Lock",     57),     # see note below
]
```

Storing `None` for Fn (not `63`) keeps "default" semantics intact — `resolve_trigger()` already maps `None` → platform default, so the same config works if the macOS default ever changes. Non-default presets store the raw keycode (int), which `decode_trigger_event`'s modifier/regular paths already handle.

> NOTE: the exact keycodes for Right Option / Caps Lock / Right Command as they arrive through the CGEventTap must be confirmed against `_KEYCODE_TO_NAME` and a real tap during implementation — `event_decode.py` lists modifier virtual codes (252-255) separately from physical F-key codes. The preset table is the one place a wrong constant would surface, so it gets the runnable check (below). Pick only keycodes that decode to a stable press+release.

**Active-trigger matching.** The checkmark/title logic compares the resolved active trigger to each preset's stored value. Because Fn is stored as `None`, "active = Fn" is `config["trigger"] in (None, "")`. A configured value not in the preset list (e.g. a hand-edited config) shows no checkmark and a title like `Trigger: key96` via `keycode_to_name` — no crash, just unlabeled.

**Live apply via listener restart.** In `update_config`, when `"trigger"` is in the updates and the listener is active, call `stop_fn_listener()` then `start_fn_listener()`. `start_fn_listener` already calls `resolve_trigger()`, so it picks up the just-saved value. Guard on `self.state.fn_listener_active` so a config update before the engine starts is a no-op (the listener will read the right trigger when it starts normally).

**UI mirrors Model/Language.** New `_on_trigger_select` callback (reads `item._trigger_value`, calls `engine.update_config({"trigger": value})`, updates checks + title), `_update_trigger_title`, and a `self._trigger_items` dict registered in `_refresh_accents` for theming. `fn_status_item` and its slot in the `self.menu` list are replaced by `self.trigger_menu`.

## Risks / Trade-offs

- **Wrong preset keycode** → a trigger that never fires or never releases. Mitigation: the runnable check asserts every non-`None` preset keycode is present in `_KEYCODE_TO_NAME` (catches typos at test time); real press/release per preset is a macos-real manual check, same tier as the existing tap scenarios.
- **Bad-for-typing keys** if the list grows. Keeping the list curated and small is the guard; document why letter/space/Esc are excluded.
- **Listener restart hiccup**: a press landing exactly during stop→start could be missed. Acceptable — the user is changing settings, not dictating, and the window is sub-millisecond. Not worth locking.
- **Linux divergence**: Linux users still edit config by hand for non-default triggers. Acceptable for v1; the menu is macOS-only anyway.

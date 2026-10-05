## Why

Editing `~/.config/whispy/config.json` by hand while Whispy is running loses the edit, silently. The user hit this and reported it as "the saved settings aren't saved".

The cause is a read-once / write-all asymmetry:

- `load_config` runs **exactly once**, at daemon boot (`whispy_daemon.py:118`). Nothing re-reads the file afterwards — there is no watcher and no reload path; `load_config` is imported into `engine.py` and never called there.
- `save_config` (`config.py:297-313`) writes **every key** in `DEFAULT_CONFIG` from the in-memory `state.config`. It is a full rewrite, not a merge.

So any `update_config` — a menu toggle, or a `POST /config` — replays a boot-time snapshot over the whole file:

```
daemon boot
   load_config(config.json) --> state.config      <- the only live copy

   ... app runs, file is never read again ...

user hand-edits config.json     (max_chunk_s 12 -> 8)
   config.json    max_chunk_s = 8                 <- the edit
   state.config   max_chunk_s = 12                <- stale, never re-read

user toggles any menu item
   update_config({"type_while_speaking": false})
      state.config["type_while_speaking"] = false
      save_config(state.config)  --> writes all 14 keys
   config.json    max_chunk_s = 12                <- edit destroyed, no warning
```

Two failures stack: the edit never takes effect (the file is read once), **and** it is destroyed by the next unrelated toggle.

This lands hardest on the settings that have no UI. Only 5 of the 14 config keys are reachable from the menu bar (`trigger`, `trigger_mode`, `copy_to_clipboard`, `type_while_speaking`, `start_at_login` — `menu_bar.py:441-477`). The other 9 — `max_chunk_s`, `min_chunk_s`, `min_speech_s`, `pause_ms`, `vad_aggressiveness`, `streaming_enabled`, `min_recording_duration`, `custom_vocabulary` — can only be changed by editing the file or calling the HTTP API. Hand-editing is the documented-by-absence route, and it is the one that silently breaks.

`max_chunk_s` is in that group, and it is the knob that governs the language-drift problem `fix-dictation-text-fidelity` exists to fix. A user following that advice by hand would watch the fix evaporate on their next menu click.

## What Changes

- `Engine.update_config` re-reads the config file, merges the requested updates on top of what is on disk, and persists the merged result. A key the caller did not touch is carried through from the file, never from the boot-time snapshot.
- **BEHAVIOUR CHANGE**: on a conflict the **file wins** for untouched keys. A hand-edit made while the app runs survives the next save, and takes effect at that point rather than only after a restart. Previously the in-memory snapshot won and the edit was discarded.
- Side effects that `update_config` already performs (listener restart, streaming re-wiring, injector reconfiguration) are driven by what **actually changed** after the merge, not by the caller's requested keys alone. Without this the merge is only half-true: a hand-edited `max_chunk_s` would reach `state.config` and the file, while the running audio engine kept the old value.
- The in-memory `state.config` dict is updated **in place**, never rebound — it is shared by reference across the engine, audio, and UI layers.

Out of scope, deliberately:

- **No config reloading.** A hand-edit still does not take effect on its own; it takes effect at the next `update_config`. Adding a watcher or an mtime poll is a separate change with a moving part, and it does not address the data loss that is the actual defect here.
- **No new settings UI.** Exposing the 9 file-only knobs in the menu bar would remove the reason to hand-edit at all, but that is discoverability work — `improve-discoverability` (13/21) already owns that territory — and it does not fix the loss for anyone who edits the file anyway.
- **No change to `max_chunk_s`'s default.** `fix-dictation-text-fidelity` owns that decision.

## Capabilities

### New Capabilities

_None — this corrects existing configuration behaviour._

### Modified Capabilities

- `core-engine`: the "Configuration Loading" requirement gains a persistence rule. A configuration update SHALL merge onto the current on-disk config rather than overwrite it with an in-memory snapshot, so a key the update does not name is preserved as the file holds it. Side effects of an update SHALL be applied for every key whose effective value changed, not only for the keys the caller named.

## Impact

- `src/whispy/core/engine.py` — `update_config` (lines 1195-1240): re-read, merge, in-place update, and change-driven side effects.
- `src/whispy/core/config.py` — likely a read-without-migrate helper. `load_config` calls `_migrate_config`, which itself calls `save_config` (`config.py:259`), so re-reading via `load_config` on every update would write the file twice per toggle.
- Tests: `tests/test_engine.py` (merge behaviour, in-place mutation, side effects on merged changes), `tests/test_config_validation.py` (the read helper).
- No new dependency. No API surface change — `POST /config` keeps its contract and gets the same fix for free, since it routes through `update_config` (`api/server.py:200`).
- No `website/index.html` change: no user-facing feature changes, and the settings themselves are unchanged.
- Validation of hand-edited values is inherited: the read path validates, so a malformed hand-edit degrades to the default instead of being merged in as garbage.

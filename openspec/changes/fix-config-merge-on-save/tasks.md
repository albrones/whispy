## 1. Split the config read path

- [x] 1.1 In `src/whispy/core/config.py`, extract the parse-defaults-validate half of `load_config` into a module-level helper (parse the file if it exists, fall back to `DEFAULT_CONFIG`, run `_validate_config`, return the dict) that does **not** migrate and therefore does **not** write; verify by asserting the helper leaves the file's mtime unchanged on a config that would otherwise migrate
- [x] 1.2 Reimplement `load_config` as that helper plus the existing migrate-if-file-loaded step, so boot behaviour is byte-identical; verify the full `tests/test_config_validation.py` passes unchanged
- [x] 1.3 Add a test that the helper degrades a malformed value to its default (e.g. `vad_aggressiveness: "loud"`) and does not raise — this is what keeps a hand-edit from merging in unchecked

## 2. Merge instead of overwrite

- [x] 2.1 In `Engine.update_config` (`src/whispy/core/engine.py:1195`), snapshot `before = dict(self.state.config)`, read the on-disk config with the group-1 helper, apply the caller's valid updates on top, and compute `changed` as the set of keys whose value differs from `before`; verify with a test that a key edited on disk since startup survives an update naming a different key (the "preserves a key edited on disk" scenario)
- [x] 2.2 Assign the merged result into `self.state.config` **in place** (`clear()` + `update()`), never by rebinding — the dict is shared by reference with `AudioEngine` and the menu bar. Leave a comment saying so; verify with a test asserting the config object's identity is unchanged across an update
- [x] 2.3 Persist with `save_config` as today, outside the lock; verify with a test that the caller's value wins over the file for a key the update names
- [x] 2.4 Take `self.state.lock` around the read-merge-assign only — not around `save_config` and not around the side effects, which join listener threads. Verify the existing engine tests still pass and no test deadlocks

## 3. Drive side effects from what actually changed

- [x] 3.1 Re-gate the `copy_to_clipboard` injector reconfiguration, the `trigger_mode` cache refresh, the `trigger` listener restart, and the streaming re-wire on `changed` instead of `updates.keys()`; verify the existing "Trigger change restarts the listener" test still passes
- [x] 3.2 Add a test that a streaming parameter edited on disk since startup is applied to the audio engine when an update naming only a non-streaming key is processed (the "merged-in streaming value reaches the audio engine" scenario)
- [x] 3.3 Add a test that an update whose values all match the current effective config restarts nothing and re-wires nothing — this pins the deliberate removal of spurious listener restarts so it is not read later as a regression

## 4. Corruption behaviour

- [x] 4.1 Add a test for an unparseable config file at update time: the update SHALL NOT raise. The test showed exactly the failure the task said to stop on — an unrelated toggle persisted `DEFAULT_CONFIG` over every user setting — so it was fixed rather than encoded: `read_config` gained a `fallback`, the engine passes the running config, and `test_a_corrupt_file_does_not_reset_the_settings_the_engine_is_running` guards it
- [x] 4.2 Cover the `fallback` at the `read_config` level too: used only when the file is missing or unparseable, validated like any other source, ignored when the file parses (`test_config_validation.py`)

## 5. Verification

- [x] 5.1 Run `./.venv/bin/pytest` — green, no new skips (933 passed, 1 skipped)
- [x] 5.2 Run `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` (ruff is pinned 0.15.21, not the 0.6.9 this task was written against) — clean
- [ ] 5.3 End-to-end by hand against the running app, reproducing the original report: note the current `max_chunk_s`, edit `~/.config/whispy/config.json` to `8.0` while Whispy runs, toggle any menu item, then confirm `max_chunk_s` is still `8.0` and the other setting took effect. On `main` this same sequence restores `12.0`
- [x] 5.4 Confirm `POST /config` inherits the fix with no API change — done against the running daemon: with `max_chunk_s` hand-edited to 9.5 on disk, `POST /config {"copy_to_clipboard": true}` returned 9.5 in the body and left 9.5 on disk. Corrupting the file and posting an unrelated key then kept 9.5 rather than resetting to the default, confirming the 4.1 fallback live: with a hand-edit pending, `curl -X POST -H "Authorization: Bearer $(cat ~/.config/whispy/config.token)" -d '{"copy_to_clipboard": true}' http://127.0.0.1:9090/config` and check the hand-edited key survives in the response body and on disk

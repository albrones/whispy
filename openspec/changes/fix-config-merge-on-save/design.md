## Context

See `proposal.md` — Why, for the defect and its measurements.

Four facts about the current code decide the approach:

**`load_config` writes.** It calls `_migrate_config` (`config.py:292`), which unconditionally calls `save_config` (`config.py:259`) to persist the migrated result. So the obvious implementation — call `load_config`, merge, call `save_config` — writes the file twice on every menu toggle, and opens a window between the two writes.

**`state.config` is shared by reference.** `AudioEngine` reads `cfg = self.state.config` and pulls values out per recording; the menu bar reads it to render toggle labels. Rebinding `self.state.config = merged` would leave every other holder pointing at a detached dict that no longer tracks updates.

**Side effects currently key off the caller's keys.** `update_config` gates the listener restart on `"trigger" in updates`, streaming re-wiring on `streaming_keys & updates.keys()`, and the injector on `"copy_to_clipboard" in updates` (`engine.py:1207-1240`). Once a merge can change a key the caller never named, that gating silently under-fires: the value lands in `state.config` and on disk while the running component keeps the old one.

**There are two writer threads.** The menu bar calls `update_config` on the AppKit main thread; the HTTP API calls it on the `http-server` thread (`api/server.py:200`). Today each call is a single `save_config`. Turning it into read-modify-write widens the critical section.

## Goals / Non-Goals

**Goals:**

- A key not named by an update survives the update with the value the file holds.
- The running engine agrees with the config it just persisted, for every key whose effective value changed.
- One file write per update, as today.

**Non-Goals:**

- Picking up a hand-edit without an update to trigger it. A watcher or mtime poll is a separate change; this one stops the loss, it does not add live reloading.
- Any change to which settings exist, their defaults, or where they are exposed.
- Multi-process safety. Whispy is single-instance by construction (the `:9090` bind), so the only writers are threads inside one process.

## Decisions

### 1. Read through a validate-without-migrate helper, not `load_config`

Split the load path in `config.py`: extract the "parse file, fill defaults, validate" half into a helper, and leave `load_config` as that helper plus the migration step.

```
load_config(path)      = _read_validated(path) + migrate-if-file-loaded   (boot)
_read_validated(path)  = parse + defaults + _validate_config              (every update)
```

`update_config` calls the helper. Boot still migrates exactly as before; updates stop triggering a spurious migration write.

*Alternatives considered.* **Call `load_config` and accept the double write.** Rejected: it doubles the write rate on a file the user may be editing by hand, which is precisely the scenario this change exists to protect — a second write between read and merge is a race we would be introducing while fixing one. **Read and `json.load` directly in the engine.** Rejected: it would bypass `_validate_config`, letting a malformed hand-edit merge in unchecked, and duplicate the defaults-filling logic that already exists.

Validation comes free with this choice: a hand-edited `vad_aggressiveness: "loud"` degrades to its default on the way in, rather than reaching the audio engine.

### 2. Merge, then diff against the pre-merge effective config

```
before  = dict(state.config)              # what the engine is actually running with
merged  = _read_validated(path)           # what the file says now
merged.update(valid keys from updates)    # caller wins for keys it names
changed = {k for k in merged if before.get(k) != merged[k]}

state.config.clear(); state.config.update(merged)      # in place — decision 3
save_config(state.config, path)
# side effects gated on `changed`, not on updates.keys()
```

`before` is the engine's own view, not the file's, so `changed` captures both the caller's updates *and* anything hand-edited since startup. That is exactly the set of keys whose running component is now out of date.

Gating on `changed` rather than `updates.keys()` also removes spurious work in the other direction: setting a key to the value it already has stops restarting the key listener. That is an observable improvement, and the spec pins it so it is not mistaken for a regression.

*Alternative considered:* keep `updates.keys()` gating and accept that merged-in values only take effect at the next restart. Rejected — it makes "the file wins" true of the file and false of the running app, which is a more confusing contract than the bug it replaces.

### 3. Mutate `state.config` in place

`state.config.clear()` then `.update(merged)`, never `state.config = merged`. See Context. Worth an explicit comment at the call site: the rebinding version looks cleaner, passes any test that only inspects `engine.state.config`, and breaks the audio engine silently.

### 4. Serialize the read-modify-write under the existing lock

`DictationState` already carries `self.state.lock`, used to guard chunk accumulation. Take it around the read-merge-assign so two concurrent `update_config` calls cannot interleave and lose one update.

Keep `save_config` and the side effects **outside** the lock: `save_config` does file I/O, and the side effects call `stop_fn_listener`/`start_fn_listener`, which join threads. Holding a lock across either invites the class of deadlock this repo has already hit once (`state_machine.py` notifies callbacks outside its lock for the same reason).

*Alternative considered:* a new dedicated config lock. Rejected as an extra object for a path that runs a few times per session; the existing lock's contention is negligible at this rate.

## Risks / Trade-offs

- **A stale hand-edit now takes effect at a surprising moment.** A user who edits the file, forgets, and toggles something a week later gets the edit applied then. → This is the contract the user chose (file wins) and is strictly better than the edit being destroyed. The `changed`-driven side effects mean it is applied consistently rather than half-applied, and every applied change is already visible in the daemon log's config path.
- **A corrupted config file now affects updates, not just boot.** If the file becomes unparseable while running, `_read_validated` falls back to defaults, and an unrelated toggle would persist those defaults over the user's settings. → `load_config` already has this failure mode at boot and logs to stderr (`config.py:284`) — which is now actually readable, since `fix-toggle-trigger-strand` routes stderr to `~/.whispy-error.log`. The explicit test showed it was unacceptable: a corrupt file plus one unrelated toggle persisted `DEFAULT_CONFIG` over every setting the user held. Resolved inside this change rather than deferred — `read_config` takes a `fallback`, and the engine passes the configuration it is running with, so an unreadable file costs only the edits that corrupted it. Aborting the update was the other option and is worse: the user's toggle would silently do nothing.
- **Two writes become a read plus a write.** → Still one write. The read is a small JSON parse on a file in the page cache, on a path that runs at human frequency.
- **The lock widens.** → Bounded to an in-memory read-merge-assign; I/O and thread joins stay outside it.

## Migration Plan

No migration. No config format change, no new keys, no defaults touched. Existing config files load exactly as before; the first update after the upgrade merges rather than overwrites.

Rollback is a revert of `update_config` — the `config.py` helper extraction is behaviour-preserving on its own and can stay.

Verification is unit-level throughout: every scenario in the spec delta is reachable with a temp config path and a mocked engine, so no live drive is required for this change.

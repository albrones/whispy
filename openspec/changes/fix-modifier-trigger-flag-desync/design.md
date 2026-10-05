## Context

See `proposal.md` — Why, for the motivation and the log evidence.

Design-relevant state of the code:

- `event_decode.py::decode_trigger_event` is pure and takes `(kind, keycode, flags, trigger_keycode, prev_flags, required_mask)`. For a non-Fn modifier it computes `changed = flags ^ prev_flags` and reads the direction off `changed & flags` / `changed & prev`.
- `event_tap.py::_event_callback` owns `self._prev_flags` and assigns it **only** on `kind == "flags_changed"`, after the decode call.
- `_TRIGGER_HELD_MASK` already exists in `event_decode.py`, mapping a trigger keycode to the modifier mask that is set while the key is held. It uses the **side-agnostic** masks (`MASK_OPTION = 0x80000`, `MASK_COMMAND = 0x100000`) and is consumed only by `trigger_held_after_rearm`.
- `NX_SECONDARYFNMASK = 0x800000` is already hardcoded in this module, so hardcoding OS constants pyobjc does not export is established practice here.
- The trigger presets in `config.py` are `("Right Option", 61)` and `("Right Command", 54)` — both are right-side keys, and both share their mask with the left-side key of the same modifier.

## Goals / Non-Goals

Goals:

- Make the modifier decode a pure function of the current event, so the class of failure "state accumulated across events drifted" cannot occur.
- Keep the change inside the pure decode module and its thin OS shell, so the regression is covered by unit tests with no Quartz and no device.

Non-Goals (beyond the proposal's):

- Filtering Whispy's own synthetic events out of its tap by event source. It would reduce the rate of desync-causing events but not the possibility; the device bit removes the possibility outright and is smaller.
- Reworking `required_mask` (combination triggers). Those resolve through `key_down`/`key_up` on a regular key and never reach the modifier branch.
- Replacing `_TRIGGER_HELD_MASK`. It answers a different question ("is the key still held now?"), is correct with side-agnostic masks for that question, and is consumed on a path this change does not touch.

## Decisions

### Decode from the device-dependent bit, not from a diff

macOS carries two families of modifier bits in `CGEventFlags`: the side-agnostic masks (`kCGEventFlagMaskAlternate` and friends) and the device-dependent bits from `IOLLEvent.h` that identify the physical key:

```
NX_DEVICELCTLKEYMASK    0x00000001    NX_DEVICERCTLKEYMASK    0x00002000
NX_DEVICELSHIFTKEYMASK  0x00000002    NX_DEVICERSHIFTKEYMASK  0x00000004
NX_DEVICELCMDKEYMASK    0x00000008    NX_DEVICERCMDKEYMASK    0x00000010
NX_DEVICELALTKEYMASK    0x00000020    NX_DEVICERALTKEYMASK    0x00000040
```

A new table keyed by trigger keycode maps `61 -> 0x40` (Right Option) and `54 -> 0x10` (Right Command), the two modifier presets that ship. `decode_trigger_event` consults it before the existing diff branch: bit set is `press`, bit clear is `release`.

**Observed on this machine** (Task 1, listen-only tap on `kCGEventFlagsChanged`), not asserted from the headers:

| key | keycode | flags on press | flags on release |
|---|---|---|---|
| Right Option | 61 | `0x00080140` | `0x00000100` |
| Left Option | 58 | `0x00080120` | `0x00000100` |
| Right Command | 54 | `0x00100110` | `0x00000100` |

Every entry matches `IOLLEvent.h`: `0x40` = `NX_DEVICERALTKEYMASK`, `0x20` = `NX_DEVICELALTKEYMASK`, `0x10` = `NX_DEVICERCMDKEYMASK`. Both Option keys carry the same side-agnostic `0x80000`, and **Left Option never touches `0x40`** — which is the proposal's mechanism observed directly rather than inferred. The constant `0x100` present on every event, press and release alike, is `NX_NONCOALSESCEDMASK` and is not a modifier bit. On release every modifier bit clears, generic and device together, so "bit clear means release" is sound.

Both shipped modifier presets are therefore confirmed, and design.md's Open Question about keycode 54 is answered: it gets a table entry.

Why over the alternatives:

- **Resync `prev_flags` from `CGEventSourceFlagsState` on every event.** Keeps the diff and adds a live read per event. It narrows the window but does not close it: two same-mask transitions inside one event still collapse, and it puts a CoreGraphics call on the tap callback — the path that must stay fast, since a slow callback is what makes macOS disable the tap in the first place.
- **Track `prev_flags` on every event kind rather than only `flags_changed`.** Strictly better than today and kept as part of this change, but it is a mitigation, not a fix: it shortens staleness without making the decode independent of history.
- **Treat every `flags_changed` on the trigger keycode as a toggle.** Smallest possible diff, and wrong: a repeated event, or an event seen while the key is already down, inverts the state permanently.

### Keep the diff as the fallback, do not delete it

Triggers reachable through `parse_trigger` include modifier names with no entry in the device table, and a user may configure a keycode the table does not know. Those keep today's behaviour exactly. This also bounds the blast radius: if the live confirmation (Task 1) shows a bit that does not behave as documented on this hardware, the fallback is already the shipped path and the table entry is simply not added.

### Report the swallowed event rather than repair it

The proposal's Non-Goals rule out synthesising a press. What remains is disclosure. `fix-toggle-trigger-strand` established that a failure invisible in the log ships unnoticed and is diagnosed by inference; the same reasoning applies to a decode that silently returns `None` on the trigger's own keycode. Rate-limiting is required because `flags_changed` on a held key can repeat.

## Risks / Trade-offs

- ~~**The device bits are not exported by pyobjc and are asserted from the headers, not observed on this machine.**~~ → **Resolved by Task 1**: all three keycodes captured live and every bit matches the header values (table above). The flag-diff fallback is retained anyway for keycodes absent from the table.
- **A keyboard or remapper that does not set device bits** (some external keyboards, karabiner-style remappers, synthetic events posted by other apps) would leave the bit clear and decode every event as `release` — worse than today, because a press would never start a recording. → The decoder treats "device bit known for this keycode" as a per-event assertion: if an event on the trigger keycode carries the side-agnostic mask but not the device bit, it is not a confirmed press; fall back to the diff for that event rather than assert `release`. Covered by a spec scenario and a unit test.
- **The fix is correct but the strand has a second cause.** The log cannot prove exclusivity — it can only show the tap was alive. → The new WARNING on an undecodable trigger event is what distinguishes the two next time: a strand with the warning present means this mechanism and needs the fallback examined; a strand with no warning at all means the event never reached the callback, which is a different investigation entirely. The FSM watchdog and `RECORDING_MAX_S` remain the backstop either way.
- **Hold mode is unaffected in principle but shares the code path.** → The existing hold-mode scenarios in `event-listener` stay in the suite unchanged and must keep passing.

## Migration Plan

No data, no config, no API surface. Ship with the rest of a normal `make reinstall`.

Rollback is a revert of the device-table lookup; the flag-diff branch it guards is left intact by this change specifically so the fallback path is never the untested one.

Validation is the live drive on this machine, in the configuration that produces the strand (`trigger: 61`, `trigger_mode: "toggle"`, `type_while_speaking: true`): dictate with Left Option exercised during the recording, then stop with Right Option, and confirm `capture closed` follows every `capture open` across a session.

## Open Questions

- ~~Whether Right Command (keycode 54, the other shipped modifier preset) sets `NX_DEVICERCMDKEYMASK` on this hardware as Right Option is expected to.~~ **Answered by Task 1**: it does (`0x00100110` on press). Both shipped modifier presets are in the table.

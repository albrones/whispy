## 1. Confirm the device-dependent bits on this machine

- [x] 1.1 Write a throwaway capture script (scratchpad, not the repo) that installs a listen-only `CGEventTap` for `kCGEventFlagsChanged` and prints `keycode` and raw `CGEventGetFlags` in hex for every event; verify it prints a line when any modifier is pressed
- [x] 1.2 Capture a Right Option (keycode 61) press and release with the script and verify the down event carries `0x40` set and the up event carries it clear, with `0x80000` behaving as the side-agnostic mask on both
- [x] 1.3 Capture a Left Option press and release and verify it moves `0x20` and `0x80000` but never `0x40` — this is the interleaving that strands the trigger today
- [x] 1.4 Capture a Right Command (keycode 54) press and release and record whether `0x10` behaves the same way; this answers design.md's Open Question and decides whether keycode 54 gets a table entry
- [x] 1.5 Record the captured hex values in design.md (replace the asserted constants with observed ones) and verify the file states which keycodes are confirmed and which keep the flag-diff fallback

## 2. Device-bit decode in the pure module

- [x] 2.1 Add the device-dependent bit table to `event_decode.py`, keyed by trigger keycode, containing only the entries confirmed in Task 1, with the `IOLLEvent.h` names in a comment; verify `openspec validate --strict` passes and the module imports with no Quartz present
- [x] 2.2 Make `decode_trigger_event` consult the table before the existing flag-diff branch for a `flags_changed` event on a modifier trigger — bit set returns `press`, bit clear returns `release`; verify new cases in `tests/test_event_decode.py` cover both directions with `prev_flags` deliberately stale
- [x] 2.3 Add the per-event assertion from design.md — an event carrying the side-agnostic mask but not the device bit falls back to the flag-diff for that event rather than asserting `release`; verify a unit test covers a keyboard that sets no device bit and still decodes press then release
- [x] 2.4 Add the regression test this change exists to prevent: Left Option held across a Right Option press still decodes `press`; verify it fails against the current `decode_trigger_event` and passes after 2.2
- [x] 2.5 Add the missed-event test: a trigger `flags_changed` never delivered, the next delivered trigger event carrying the device bit set decodes `press`; verify it passes without any resynchronisation call
- [x] 2.6 Verify the Fn path (keycode 63, `NX_SECONDARYFNMASK`), the no-device-bit fallback, and the `required_mask` combination path are untouched by running the existing `tests/test_event_decode.py` suite green
- [x] 2.7 Correct `_KEYCODE_TO_NAME` in `event_decode.py` against Carbon's `<HIToolbox/Events.h>`. The table was written from memory and wrong from keycode 9 onward: the right-hand modifier block carried `f1`-`f4`, so Right Option printed as `f3` in the menu bar (`menu_bar.py:242`) and in the startup log, Right Command (54, a trigger preset) was absent, and `255` claimed to be `command`. Because `parse_trigger` resolves hand-written string triggers through the reverse of this table, `ctrl+alt+cmd+p` bound the quote key. Verified by `test_every_trigger_preset_names_the_key_it_is`, `test_the_keycodes_this_table_used_to_get_wrong` and a round-trip assertion over the whole table

## 3. Listener shell

- [x] 3.1 Update `_event_callback` in `event_tap.py` to track `self._prev_flags` from every event that carries flags, not only `flags_changed`; verify a unit test asserts `_prev_flags` is current after a `key_down`
- [x] 3.2 Report an event on the configured trigger keycode that decodes to neither press nor release, at WARNING, with the event kind and the observed flags; verify `tests/test_event_tap.py` asserts the warning fires for the trigger keycode
- [x] 3.3 Rate-limit that warning so a repeating condition cannot flood the daemon log; verify a unit test drives many undecodable events and asserts the log line count is bounded
- [x] 3.4 Verify no warning is emitted for an event whose keycode is not the configured trigger, with a unit test

## 4. Verification on the machine that produces the strand

- [x] 4.1 Run the full suite with `./.venv/bin/pytest` and verify it is green, with particular attention to `tests/test_event_tap.py`, `tests/test_event_tap_e2e.py` and `tests/test_engine.py`
- [x] 4.2 `make reinstall`, then verify the daemon answers on `:9090` and `~/.whispy.log` shows the trigger listener active — the daemon came up on `:9090`, but the log held no listener line at all (the message was a `print` to stdout, which the bundled `.app` discards; fixed as `fix-toggle-trigger-strand` 1.5), and once it appeared it read `key: f3` for a `trigger` of 61. See 2.7
- [ ] 4.3 Live drive in the strand configuration (`trigger: 61`, `trigger_mode: "toggle"`, `type_while_speaking: true`): dictate several recordings while deliberately using Left Option during each, stopping with Right Option; verify every `[audio] capture open` is followed by a `[audio] capture closed` in `~/.whispy.log`
- [ ] 4.4 Verify no `watchdog: RECORDING hit the 300s limit` and no undecodable-trigger warning appear during 4.3 — a warning present would mean the fallback path is being taken and the table entry needs re-examining
- [ ] 4.5 Confirm the counts over the drive: `grep -c "capture open" ~/.whispy.log` equals `grep -c "capture closed" ~/.whispy.log` for the lines produced after the reinstall

## 5. Close out

- [x] 5.1 Verify `openspec validate fix-modifier-trigger-flag-desync --strict` passes
- [x] 5.2 Task 2.7 does change what the user sees: the menu bar's trigger item now names a modifier trigger correctly (Right Option was shown as `f3`). `website/index.html` still needs no update — its menu mock shows the default `Fn` trigger, whose name was already right — and `tests/test_website.py` passes

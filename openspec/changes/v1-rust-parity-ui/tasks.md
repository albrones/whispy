# Tasks

## 1. Base

- [x] 1.1 Branch from `origin/main` and move this change's directory onto the branch. Verify that `cargo test --release` passes in `v2/` before any edit.
- [x] 1.2 Move the hand-written JSON reader (`Json`, `parse_json`) from `banc/src/labelled.rs` to `whispy-core/src/json.rs`, and add a serialiser that round-trips integers, floats, strings (escaped), booleans, null, arrays and objects. Verify `banc`'s existing tests still pass, and that new round-trip tests pass, including on a copy of a real V1 `config.json` shape.

## 2. Settings (V1's file)

- [x] 2.1 Add `whispy2/src/settings.rs`: `load(path)` with V1's defaults and validation for `copy_to_clipboard`, `trigger_mode` and `trigger` (a combination string falls back to Fn with a note), and `save_key(path, key, value)` that re-reads, sets one key, keeps every other key, writes tmp + rename at 0600 in a 0700 dir, and refuses when the file is unreadable. Verify the spec scenarios as unit tests: V1's choices are picked up, a broken file does not stop the app, V1-only keys survive, an unreadable file is not replaced.
- [ ] 2.2 Load the settings at startup in `main.rs` and pass them to the controller. Log the effective values (never the file's other keys). Verify that the startup log line shows the user's real values.

## 3. Trigger: mode and key

- [x] 3.1 Add `TriggerMode` to `machine.rs`. Hold: under 0.3 s the press is discarded, with no latch. Toggle: a press starts, the next press stops, and releases are ignored. A mode change applies at the next idle. Rewrite the latch tests as toggle-mode tests and keep the watchdog, modifier-cancel and V1-yield tests. Verify that `cargo test -p whispy2 machine` passes, including « a short press in hold mode is discarded ».
- [ ] 3.2 Replace `mac/fn_key.rs` with `mac/trigger_tap.rs`. The keycode is held in an atomic: modifiers (63, 54, 61) are read through the device flag bits, other keys through KeyDown/KeyUp with autorepeat ignored. Update `revive` per key kind. Keep the pure decoding in a portable function with unit tests (Right Command vs Left Command, F13 autorepeat). Verify the unit tests pass, then by hand: Right Option starts a dictation when it is the trigger, and Fn does nothing.
- [x] 3.3 Adapt the socket's `toggle` to one toggle-mode press (in hold mode: start when idle, stop when recording). Update the `control` tests and the README protocol lines. Verify the tests pass and that `printf 'toggle\n'` twice dictates in either mode.

## 4. Delivery

- [ ] 4.1 Add typed delivery to `mac/inserter.rs`: `copy_to_clipboard=false` runs `osascript` `on run argv … keystroke (item 1 of argv)` with the text as argv, without touching the clipboard, and maps 1002 to the Accessibility message. Build the command in a pure function. Verify the unit tests (argv carries the text, the injection string stays literal), then by hand: typing into TextEdit with the clipboard unchanged (`pbpaste` before and after).

## 5. Menu, title, theme

- [x] 5.1 Add `title_anim.rs`, with V1's `WAVEROWS`, `IDLE_FRAME`, the 90 ms interval, `select_frame` and V1's MIT attribution. Verify unit tests ported from V1's `test_unicode_anim`-style cases.
- [x] 5.2 Add `menu_model.rs`, which builds V1's ordered rows from Status, Settings, login state and appearance: status texts, the trailing ✓ on toggles, the leading ✓ or aligned blank on submenu choices, the SETTINGS header, the accent ranges, the hidden permission row, the yielded line, and the « Trigger: <label> » title (preset label, else keycode name). Add `theme` colours (#24bf9e dark, #1c9a7f light). Verify the « menu matches V1 » and « appearance switch » scenarios as unit tests.
- [ ] 5.3 Rewrite `mac/menu_bar.rs` to render the model: attributed titles, kern on the header, submenu, tag-based action target for Copy to clipboard, Toggle mode, the Trigger presets, Start at login (existing login_item behaviour), Restart, permission item and Quit ⌘Q. Rebuild on `menuWillOpen:` and on status change. Run the 90 ms title timer on the main run loop, with no image, re-rendering on an appearance flip. Verify by hand, reading the menu through the Accessibility API against the scenario list, and watch the title animate during a dictation.
- [ ] 5.4 Wire the menu actions to `settings::save_key` and to live controller updates (`Event::Settings`, trigger keycode swap). Verify: a toggle in the menu changes `config.json` (only that key) and applies to the next dictation without a restart.
- [ ] 5.5 Implement Restart (design §8): a detached waiter until the socket stops answering (5 s cap), then `open` the bundle or re-exec outside a bundle, then the normal Quit. Verify the « Restart hands over » scenario: a new process answers within 10 s and exactly one remains.

## 6. Recording pill

- [x] 6.1 Add the pure `pill_geometry.rs`: V1's level scale (`min(rms×10,1)`), smoothing step, display curve (`level^0.5×2`, capped), envelope, wobble, bar heights 5–38 pt, colour by level, and placement 40 pt up and centred in a visible frame. Verify unit tests, including « bars follow the voice ».
- [ ] 6.2 Add `mac/pill.rs`: the `NSPanel` with V1's style, level, collection behaviour (re-applied on each show) and click-through, a custom `drawRect:` view, a 30 fps timer with fade in/out and `orderOut` below 0.02, all on the main thread. Implement `Feedback` with V1's lifecycle: show on trigger press or recording start, hide on recording stop or discard. Delete `mac/indicator.rs`. Verify by hand: the pill looks like V1's side by side (screenshot of each), appears over a full-screen app, and the focus stays.

## 7. Alerts and notifications

- [x] 7.1 Extend `Feedback::alert` to an `Alert { subtitle, message, pane }` with V1's strings for the seven events, and map the controller's existing notes and the watchdog, load and permission errors onto them. Verify controller unit tests: each event yields the V1 subtitle, and a permission alert carries its pane.
- [ ] 7.2 Add `mac/notify.rs` (`objc2-user-notifications`, pinned `=` and justified in a Cargo comment): request authorisation once from the bundle, skip outside a bundle, and post title « Whispy » with the subtitle and message. The permission item opens V1's `x-apple.systempreferences` URL for its pane. Verify by hand: a deaf take posts « Microphone heard nothing », and clicking the warning item opens Input Monitoring.

## 8. Docs and integration

- [ ] 8.1 Update `v2/README.md`: the menu, settings shared with V1 (which keys, merge-on-save, start at login still per app), trigger presets and modes, typed delivery, the pill and notifications. Check every documented menu label against the model.
- [ ] 8.2 Run `cargo fmt --check`, `cargo clippy --release --all-targets -- -D warnings` and `cargo test --release` in `v2/`, and the root `./.venv/bin/pytest` to confirm V1 is untouched. All green.
- [ ] 8.3 End to end on this Mac with `make v2-reinstall`. With the user's real settings (Right Option, toggle, typed): dictate into TextEdit. Then switch in the menu to Fn hold with clipboard, and dictate again. Check `config.json` keeps its other keys and the journal records both. Record the result here.
- [ ] 8.4 Verify `openspec validate v1-rust-parity-ui --strict` passes.

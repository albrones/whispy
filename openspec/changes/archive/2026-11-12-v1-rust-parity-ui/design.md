## Context

V1's interface lives in two files:
- `src/whispy/ui/menu_bar.py` (rumps): the menu, the status line, alerts and the 90 ms title timer;
- `src/whispy/ui/waveform_window.py`: the pill, an `NSPanel` hosting a custom `NSView` drawn with `NSBezierPath` at 30 fps.

Their helpers are `menu_theme.py`, which builds attributed titles, and `unicode_anim.py`, which holds the braille frames. Settings come from `core/config.py`, whose `CONFIG_SCHEMA` sets keys, defaults and validation. V1 **drops unknown keys** when it validates a file, and saves atomically (tmp file, 0600, `os.replace`).

The Rust app (`v2/whispy2`) today has:
- `mac/menu_bar.rs`: an `NSStatusItem` with a microphone image and a short menu, refreshed through `menu_bar::show(Status)` on the main queue;
- `mac/indicator.rs`: a grey `NSPanel` behind the portable `Feedback` port (`show(Phase)`, `level`, `alert`);
- `mac/fn_key.rs`: a listen-only tap on keycode 63 only;
- `machine.rs`: a pure state machine with a hybrid trigger, where a tap under 0.3 s latches and a hold dictates;
- `control.rs`: a socket mapping `start`/`stop`/`toggle` to `FnDown`/`FnUp`.

## Goals / Non-Goals

**Goals:**
- Someone who knows V1 should not be able to tell from the menu, the title or the pill that the app is not V1, apart from the « Whispy V2 » bundle name and the V1-cohabitation status line.
- Every pure decision has a unit test, with no AppKit: frame selection, bar heights, colour per appearance, settings parsing and merging, trigger decoding, menu model.
- The `Feedback` port and the `mac/` split stay, so a Linux tray can take the same events later.

**Non-Goals:**
- Streaming and live typing (« Type while speaking »), vocabulary, and the rest of V1's config keys.
- Renaming the bundle, and sharing `start_at_login`. Both belong to the switchover.

## Decisions

### 1. A pure menu model, rendered by a thin AppKit layer
New `menu_model.rs` (portable) holds `MenuModel::from(&Status, &Settings, LoginState, Appearance)`, which returns an ordered list of rows. Each row has a kind (header, status, warning, section, toggle, submenu, separator, action), a plain title, `checked`, `enabled`, and accent ranges given as character offsets.

`mac/menu_bar.rs` only turns rows into `NSMenuItem`s with `setAttributedTitle` (`NSForegroundColorAttributeName` on the accent ranges, `NSKernAttributeName` 1.5 on the header). It keeps one action target, a `define_class!` like today's `QuitTarget`, that maps an item tag to a `MenuAction`.

The menu is rebuilt in `menuWillOpen:` and on each status change, which is cheap at about 12 items. This makes the "menu matches V1" scenario a plain unit test on the model.

*Alternative:* mutating long-lived items, as V1 does through rumps. It is more state to keep in sync, and the model would not be testable.

### 2. Title animation on a main-thread timer
`title_anim.rs` (portable) holds V1's `WAVEROWS`, `IDLE_FRAME` and `select_frame(index, active)`, ported verbatim with V1's MIT attribution comment.

An `NSTimer` at 90 ms on the main run loop reads an `Arc<AtomicBool>` "active" flag. The controller sets the flag when the trigger is down, while recording, while transcribing and while models load. The timer also polls the appearance and triggers a menu re-render when it flips, as V1's `_tick_anim` does.

The image is dropped: `button.setImage(None)`, `button.setTitle(frame)`.

### 3. The pill is a custom NSView ported from `waveform_window.py`
`mac/pill.rs` defines `Whispy2PillView` (`define_class!`, `drawRect:`). It draws the rounded background and the 11 bars with `NSBezierPath`. The panel setup is V1's:
- borderless | non-activating;
- `NSScreenSaverWindowLevel`;
- collection behaviour `MoveToActiveSpace | FullScreenAuxiliary | IgnoresCycle`, re-applied on each show, as V1 found it must be;
- clear background, shadow, ignores the mouse;
- `NSScreen::mainScreen` visible frame, 40 pt up.

A 30 fps `NSTimer`:
- smooths the level toward its target (`dt × 8`);
- advances the wobble phase (`dt × 6`);
- fades alpha (`dt × 4.5`);
- calls `orderOut` once faded below 0.02.

The level arrives through `Feedback::level` (RMS from the microphone, throttled to 20 Hz) and is converted to V1's scale (`min(rms × 10, 1)`).

The bar geometry lives in a pure `pill_geometry.rs`: bar heights from (level, phase) and placement from the visible frame. It is unit-tested.

`Feedback::show(Phase)` maps to V1's lifecycle:
- show on `TriggerDown` (Listening) or `Recording`;
- hide on recording stop or on a discarded press.

`Phase::Transcribing` becomes "hide", as in V1. `mac/indicator.rs` is deleted.

### 4. Settings: the V1 file, three owned keys, merge-on-save
`settings.rs` (portable) holds `Settings { copy_to_clipboard, trigger_mode, trigger }`.

`load(path)` parses with a small hand-written JSON reader. The workspace has no serde; reuse `banc::labelled::parse_json` by moving it to `whispy-core` as `json.rs`. It validates against V1's rules:
- bool;
- `"hold"|"toggle"`;
- null, an integer keycode, or a string combination, which falls back to Fn with a note.

`save_key(path, key, value)` runs these steps:
1. re-read the file as a generic JSON object; if that fails, refuse (spec);
2. set the one key;
3. serialise all keys back, preserving unknown keys and their values;
4. write `config.json.tmp` (0600) and `rename`.

Order and whitespace are not preserved, since V1 rewrites the file wholesale too. Number formatting must round-trip V1 values: integers stay integers, floats are written with Rust's shortest representation.

*Alternative:* adding `serde_json`. It would be the first serde in the tree, and the JSON reader already exists in `banc`. One file of round-trip tests is cheaper than a new dependency policy.

### 5. Trigger: V1's `trigger_mode` in the machine, the keycode in the tap
`machine.rs` gains `TriggerMode { Hold, Toggle }`, set by an `Event::Settings(TriggerMode)` that applies at the next idle:
- **Hold:** down → record; up ≥ 0.3 s → transcribe; up < 0.3 s → discard. There is no latch, which removes today's tap path.
- **Toggle:** down while idle → record; down while recording → transcribe; up is ignored.

The watchdog, the modifier-cancel rule, yielding to V1 and the existing tests carry over. The latch tests are rewritten for Toggle mode.

`mac/fn_key.rs` becomes `mac/trigger_tap.rs`, holding a `TriggerKey { keycode, kind: Modifier(flag) | Key }`:
- for 63, 54 and 61 it reads `FlagsChanged` with that keycode, and the down state comes from the device-specific flag bit (`NX_DEVICERCMDKEYMASK` 0x10, `NX_DEVICERALTKEYMASK` 0x40, `SecondaryFn` for Fn);
- for F13 (105) or any other keycode it reads `KeyDown`/`KeyUp`, ignoring autorepeat (`kCGKeyboardEventAutorepeat`).

The keycode is held in an `AtomicI64` read by the callback, so a menu change swaps the key without recreating the tap. The tap's event mask covers FlagsChanged, KeyDown and KeyUp.

`TapHealth::revive` checks the state of the current trigger key: flags for modifiers, `CGEventSourceKeyState` for keys.

The socket keeps its words. `toggle` becomes "one Toggle-mode press": in Hold mode it starts when idle and stops when recording, so it no longer sends a down/up pair that Hold would discard. `stop` keeps its "counts as a hold" stamp.

### 6. Typed delivery through System Events, text as data
When `copy_to_clipboard` is false, the inserter runs
`osascript -e 'on run argv' -e 'tell application "System Events" to keystroke (item 1 of argv)' -e 'end run' -- <text>`.
The text is an argv item, never interpolated into the script, which satisfies the injection scenario. The clipboard is not touched. Error 1002 maps to the same Accessibility message as the paste.

### 7. Notifications with UNUserNotificationCenter
`mac/notify.rs` uses `objc2-user-notifications` (pinned `=`, features trimmed to `UNUserNotificationCenter`, `UNMutableNotificationContent` and `UNNotificationRequest`). It requests `alert|sound` authorisation once at startup, from the bundle; outside a bundle the center is unavailable, so it is skipped.

`Feedback::alert` grows into `alert(Alert)`. An `Alert` carries `{ kind, subtitle, message, settings_pane: Option<Pane> }`, with V1's strings. The controller already produces heard-nothing notes; the other V1 alerts map to existing notes:
- the model-load error;
- microphone open failure;
- Input Monitoring or Accessibility missing;
- the watchdog stop;
- a dictation ended while models were loading.

The permission item stores the last `Pane`. Its click runs `open x-apple.systempreferences:com.apple.preference.security?Privacy_<Pane>`, with V1's URLs.

*Alternative:* the deprecated `NSUserNotification`. It is what rumps used, but it is deprecated and silently dropped on recent macOS for non-notarised apps.

### 8. Restart through the socket hand-over
Restart spawns a detached `/bin/sh -c` waiter. The waiter polls `~/.whispy/v2/control.sock` until nothing answers (5 s max, as V1 does), then runs `open "<bundle path>"`. The app then quits through the normal Quit path, which removes the socket and frees the models.

Outside a bundle, Restart re-executes `std::env::current_exe()` instead.

## Risks / Trade-offs

- **[Two apps write `config.json`]** If V1 and V2 each save a different key at the same moment, one write can win over the other. → Only one app answers the trigger at a time, saves happen only on menu clicks, and V2 re-reads before each write. The window is a human double-click across two menus. Accepted.
- **[V1 drops keys V2 might add]** → V2 writes only V1 keys (design §4). The proposal records that `start_at_login` stays OS-only until the switchover.
- **[Hold mode now discards short presses]** A user who got used to V2's tap-to-latch loses it. → It is V1's behaviour, the reference. The migration note in the spec points to Toggle mode.
- **[Notification permission]** If the user denies notifications, alerts only reach the log, the menu note and the Basso sound. → The spec allows this; V1 behaves the same.
- **[Custom drawing in Rust objc2]** `define_class!` with `drawRect:` and timers are new in this codebase. → The geometry is pure and tested, the view only paints the rectangles it is given, and the menu-bar code already has two `define_class!` targets as patterns.
- **[The JSON round trip loses the formatting of hand edits]** → V1 also rewrites the file. Values and unknown keys are kept, which is what the spec requires.

## Migration Plan

1. Implement on a branch from `origin/main`, then run `make v2-reinstall`.
2. On its first start, V2 reads the user's current settings from V1's file. Checked on 2026-11-05, the file holds `trigger: 61` (Right Option), `trigger_mode: "toggle"` and `copy_to_clipboard: false` (typed delivery). After this change, V2 will therefore answer Right Option in toggle mode and type the text, instead of today's Fn hold and paste. That is V1's behaviour, the reference. The user can switch back from the menu, and the PR says so up front.
3. Rollback: reinstall the previous V2 build from `main`. The config file is unchanged except for keys the user toggled.

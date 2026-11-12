## Why

On 2026-11-05 the user settled what V2 is for: not a second Whispy, but **V1 rewritten in Rust**. V1's design and fixes are the reference, and in the end there is one app. Today the Rust app (`v2/whispy2`) works, but it does not look or feel like V1:

- the menu bar shows a microphone icon instead of V1's braille waveform;
- the menu is a minimal one, not V1's branded menu;
- there is no Settings section;
- a grey panel stands in for V1's green audio-reactive pill;
- warnings appear only in the menu, never as notifications.

This change is the first parity step. It covers the interface the user sees and touches on every dictation. The rule throughout: V1's code and specs say what "right" is.

## What Changes

- **Menu bar title**: V1's braille waveform (`⣀⣤⣶⣤` at rest). It scrolls the 16 `waverows` frames every 90 ms while the app is listening, recording, transcribing or loading. It replaces the microphone icon.
- **Menu**, with V1's structure and wording:
  - « Whispy · voice dictation » header;
  - a status line with a green dot, using V1's states (Listening…, Loading model…, ⚠ Model not loaded, Recording, Transcribing…, Ready). While V1 still holds the trigger, a V2-only status line says « Whispy V1 is running ».
  - a hidden « ⚠ Missing permission — fix in System Settings… » item, revealed by a permission problem. It opens the matching System Settings pane.
  - a green, uppercase, letter-spaced **SETTINGS** header;
  - the settings rows: **Copy to clipboard**, **Toggle mode**, the **Trigger** submenu with V1's presets (Fn, Right Command, Right Option, F13) and **Start at login**. Toggles carry V1's trailing green ✓ and submenu choices its leading ✓.
  - **Restart** and **Quit** (⌘Q).
  - Brand green adapts to light and dark menus and re-renders when the appearance changes.
- **Settings are V1's settings, in V1's file.** V2 reads and writes `~/.config/whispy/config.json`, using V1's keys and defaults: `copy_to_clipboard`, `trigger_mode`, `trigger`. It preserves every key it does not own, so switching between V1 and V2 keeps the user's choices.
  - **Copy to clipboard** off types the text with System Events `keystroke`, as in V1.
  - **Toggle mode** follows V1's `trigger_mode`: in hold mode you hold to dictate; in toggle mode one press starts and the next one stops.
  - **Trigger** listens to the chosen key, applies live and needs no restart.
  - **Start at login** gets V1's row and styling, but its state stays the OS registration of the V2 bundle until the switchover. Sharing V1's `start_at_login` key now would make both apps register themselves at login. V1 also drops unknown keys when it validates its config, so a V2-only key cannot live in that file.
- **Recording pill**: V1's pill, ported. It is 168×52 pt and rounded, with 11 brand-green bars driven by the input level on V1's scale (RMS × 10, smoothed). Bars use a symmetric envelope and a wobble, render at 30 fps and fade in and out. The pill sits bottom-centre of the main screen, above every Space including full-screen ones. It appears on trigger press and hides when the recording ends. It replaces V2's grey `NSPanel`.
- **Notifications**: V1's alerts are posted as macOS notifications, with V1's titles and messages: missing permission, can't type into apps, model failed to load, no microphone, microphone heard nothing, dictation stopped, model still loading.
- **BREAKING (V2 only)**: V2's always-on hybrid trigger, where a short tap latches and a hold dictates, gives way to V1's explicit `trigger_mode`.

## Capabilities

### New Capabilities
- `v2-settings`: V2 reads and writes V1's config file, owns the keys listed above, applies them live, and preserves the rest.

### Modified Capabilities
- `v2-menu-bar-app`: menu, title animation, status lines, notifications and the pill now follow V1. The trigger follows V1's `trigger_mode` and `trigger`. The « Start at login » row takes V1's styling; its behaviour, defined in `v2-macos-install`, is unchanged.

## Raison d'être

- **Usage:** every dictation (title, pill) and every settings change. This is the part of the app the user looks at.
- **Without it:** V2 stays "another app". The user prefers V1's design, so the Rust port has to look like V1 before it can replace it.

## Refusé

- **Type while speaking.** It drives live typing, which needs streaming, and V2 does not stream yet. The menu row is left out until the streaming parity change brings the behaviour. Leaving it out is better than showing a toggle that does nothing.
- **Trigger key combinations.** V1 accepts them only by editing the config by hand. A combination in the config falls back to Fn with a note, and porting them can come later.
- **Sharing `start_at_login` with V1.** It moves to V1's key at the switchover, when there is a single bundle to register.
- **Renaming to Whispy / `com.whispy`.** This belongs to the switchover change, once parity is reached. Until then the bundle stays « Whispy V2 », so V1 can still be opened.
- **The ferrofluid sphere.** V1's `recording-visualization` spec still describes a ferrofluid sphere, but V1's shipped code draws the 11-bar pill. The pill is what the user knows, so the pill is ported. Fixing the V1 spec's stale text is left to a later V1 spec cleanup.
- **The Linux tray.** It belongs to a later change. The pill and the menu stay behind the `Feedback` port and in `mac/`.

## Impact

- **Code:**
  - `v2/whispy2/src/mac/menu_bar.rs`, rewritten;
  - new `mac/pill.rs` (replacing `mac/indicator.rs`), `mac/theme.rs`, `mac/notify.rs`;
  - new portable `settings.rs` and `title_anim.rs`;
  - `mac/fn_key.rs`, which becomes a configurable trigger tap;
  - `machine.rs`, to follow `trigger_mode`;
  - `controller.rs`, for status states and live settings;
  - `mac/inserter.rs`, for keystroke delivery.
- **Dependencies:** possibly `objc2-user-notifications` (pinned) for notifications. AppKit features for drawing (`NSBezierPath`, `NSColor`, `NSTimer` or a display link).
- **Shared state:** `~/.config/whispy/config.json` is now written by both apps. Writes are merge-on-save, following V1's own fix in `fix-config-merge-on-save`.
- **Docs:** `v2/README.md`. V1, its specs, the website and the socket protocol are untouched.

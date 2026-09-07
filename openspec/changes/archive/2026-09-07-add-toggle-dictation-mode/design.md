## Context

The trigger path is a single funnel. Both platform listeners — the macOS
`CGEventTap` shell (`hardware/event_tap.py`) and the Linux `pynput` shell
(`platform/linux/hotkey.py`) — decode their raw events through pure functions in
`hardware/event_decode.py` and emit the same two-word vocabulary onto one queue:

```
   CGEventTap (listen-only)              pynput (X11)
        │ keycode + flags                     │ key name
        ▼                                     ▼
   decode_trigger_event()               decode_key_match()
        │        "press" / "release"          │
        └─────────────────┬───────────────────┘
                          ▼
                 _trigger_queue  (FIFO)
                          ▼
              _trigger_worker_loop            ◄── one cross-platform seam
                 press   → _handle_trigger_press_work()
                 release → _handle_trigger_release_work()
                          ▼
        StateMachine  IDLE → RECORDING → TRANSCRIBING → IDLE
                          ▼
              on_recording_start / on_recording_stop
                          ▼
                    pill + waveform
```

Relevant current behavior:

- `_trigger_worker_loop` is the only place that maps the press/release vocabulary
  onto engine actions, and it already runs off the OS listener threads. Toggle
  semantics belong here and nowhere else.
- The pill and waveform are driven by `on_recording_start` / `on_recording_stop`
  (`ui/menu_bar.py`), not by key state. Toggle mode requires no UI state work.
- `decode_trigger_event` matches exactly one key: `if keycode != trigger_keycode:
  return None`. There is no notion of a required modifier mask.
- The event tap is deliberately `kCGEventTapOptionListenOnly`, which needs only
  Input Monitoring. It therefore **cannot** consume an event: whatever
  combination is chosen also reaches the frontmost application.
- `_wait_trigger_released()` blocks injection (bounded, 10 s) while `_fn_pressed`
  is set, because a held modifier turns injected characters into their
  Option/Command-layer variants.
- The watchdog's `_force_recover()` clears `_chunk_texts` under the state lock.

## Goals / Non-Goals

**Goals**
- A dictation that outlives the key press, on both platforms, from one code path.
- Hold mode unchanged on every path, including timing and event ordering.
- No configuration in which the app can silently discard transcribed text.
- The combination decode stays pure and unit-testable without a live event source.

**Non-Goals**
- Per-trigger language, multiple simultaneous triggers, streaming-parameter
  changes (see proposal Non-Goals).
- Making the trigger combination unavailable to the focused application.

## Decisions

### D1 — Toggle lives in `_trigger_worker_loop`, not in the listeners

The listeners are OS shells whose job is to turn raw events into `press` /
`release`. Putting a mode branch in each would duplicate the semantics twice and
make the macOS and Linux behaviors drift independently. The worker already owns
the mapping from that vocabulary to engine actions.

```
press:
    toggle mode and FSM is RECORDING  → _handle_trigger_release_work()
    otherwise                         → _handle_trigger_press_work()

release:
    toggle mode → _notify_fn_released()   only
    otherwise   → _handle_trigger_release_work()
```

### D2 — `trigger_mode` is a separate config key, not a property of the preset

Carrying the mode inside `TRIGGER_PRESETS` would mean every trigger appears twice
in the submenu (4 existing + 2 new presets × 2 modes = 12 entries). A separate
key composes: any trigger × either mode, one checkbox, and a value that is
explicit and independently validatable when the config file is hand-edited.

### D3 — Toggle mode must still process the physical release

The obvious implementation ignores `release` entirely in toggle mode. That is a
trap: `_notify_fn_released()` is what clears `_fn_pressed`, and
`_wait_trigger_released()` spins on that flag before every injection. Left set,
it would add the full `TRIGGER_RELEASE_INJECT_TIMEOUT_S` (10 s) to every
dictation.

It is not only a latency bug. In streaming mode the assembled text is injected
almost immediately after the stopping press, so if the combination's modifiers
are still physically down, the injected characters are mangled into their
modifier-layer variants.

The flag must therefore track the *physical* key state on every press and
release, including the stopping press -- which arrives with the keys down.

Crucially, this is the flag alone, not the notification. `_notify_fn_released`
does two things: it clears the flag and it fans the release out to subscribers,
and the menu bar hides the waveform pill on that event. In toggle mode the key
is released seconds before the dictation ends, so fanning out hides the pill
mid-recording (found in live-drive). Toggle mode therefore clears the flag
directly, and the stopping press stops through a `_stop_and_signal` helper that
announces nothing. The pill's lifecycle belongs to the recording
(`on_recording_start` / `on_recording_stop`), never to the key.

### D4 — Hyper (`⌃⌥⌘`) because the tap cannot swallow

With a listen-only tap, the trigger combination is delivered to the focused
application as well. A contested combination therefore fires that application's
own shortcut on both the start press and the stop press. Worse, combinations that
open a focused panel (search fields, "go to" dialogs) steal focus, so the
subsequent injection lands in the wrong field — the feature fails silently rather
than merely annoying.

The existing presets (Fn, Right Command, Right Option, F13) were chosen for
exactly this reason: they are inert on their own. `⌃⌥⌘` is the only multi-key
tier with the same property by convention.

Rejected alternative: switching the tap to `kCGEventTapOptionDefault` and
returning `None` on a match. It would allow any combination, and Accessibility —
its additional requirement — is already granted for `osascript` injection. It was
rejected because a listen-only tap that misbehaves costs a hotkey, while an active
tap that misbehaves eats keystrokes system-wide; because the OS already disables
the tap periodically (`kCGEventTapDisabledByTimeout`, handled in
`event_tap.py`), which would make swallowing intermittent and therefore
unpredictable; and because `pynput` has no selective suppression, so Linux could
not follow and the two platforms would need separate specifications.

### D5 — Two combination presets, labelled by their keys

`⌃⌥⌘E` and `⌃⌥⌘F` are added as ordinary single-selection presets with identical
behavior. They are **not** labelled with a language. The intended use — one
combination per dictation language — is blocked upstream (see proposal
Non-Goals), and a menu entry reading "French" that changes nothing would be worse
than no entry at all. Adding the presets now means the eventual language change,
if the spike succeeds, only introduces the trigger→language map.

### D6 — The recording limit stops gracefully instead of discarding

`RECORDING_MAX_S` stays at 300 s: in toggle mode a five-minute recording almost
always means the user forgot to stop. What changes is the response. The current
`_force_recover()` clears `_chunk_texts`, which under toggle mode destroys real
transcribed speech.

The new path stops the audio engine, lets the normal drain-and-assemble run, and
delivers the result to the **clipboard** rather than injecting it, then posts a
notification. Clipboard rather than injection because after five minutes there is
no reason to believe the originally focused field is still focused; typing a long
block into an unknown target is its own failure. `_force_recover()` remains as the
fallback if the graceful stop itself raises.

This applies in both modes. Discarding transcribed text is never the desired
outcome, and keeping one path avoids a mode-conditional recovery branch.

### D7 — Combination decoding stays pure

`decode_trigger_event` gains a required-modifier-mask parameter; a pure
`parse_trigger("ctrl+alt+cmd+e") -> (keycode, mask)` performs the config→match
translation. Canonical form is lowercase, `+`-separated, in the fixed order
`ctrl+alt+cmd+shift+<key>`. The mask constants mirror the `CGEventFlags` values
already present in `_TRIGGER_HELD_MASK` (Command `0x100000`, Option `0x80000`),
extended with Control `0x40000` and Shift `0x20000`.

On Linux the equivalent lives in `decode_key_match`, fed by a set of currently
held modifiers that `PynputHotkeyListener` tracks — `pynput` reports modifiers as
ordinary key events, so the listener maintains the set and the decision stays in
the pure function.

## Risks / Trade-offs

- **The combination still reaches the focused app.** Mitigated by choosing an
  inert tier, not eliminated. Accepted knowingly (D4).
- **A forgotten toggle records for five minutes.** Mitigated by D6: the text is
  preserved and the user is told. The alternative — a shorter limit — would clip
  legitimate long dictations.
- **`_KEYCODE_TO_NAME` is wrong across its letter block** (it maps `8` to `"e"`
  where `8` is C, and has no entry for `14`, the real E). Only the entries the new
  presets depend on are corrected here; a full audit of the table is noted as
  follow-up rather than folded into this change. The existing
  `test_config_validation.py` guard only requires that integer preset keycodes
  appear in the table, and the new presets are strings, so the guard is unaffected.
- **Double-press races.** Two presses arriving faster than the FSM transitions are
  serialized by the existing FIFO worker; the second is evaluated against the
  state the first produced. A press landing during TRANSCRIBING starts a new
  recording, matching today's hold-mode behavior (`StateMachine.start_recording`
  force-resets TRANSCRIBING to IDLE).

## Migration

`trigger_mode` defaults to `"hold"`. An existing config without the key is
migrated by the standard missing-default fill in `_migrate_config`, so current
installs keep push-to-talk with no behavior change and no user action.

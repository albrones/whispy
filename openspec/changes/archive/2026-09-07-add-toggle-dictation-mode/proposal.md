## Why

Whispy is push-to-talk only: the trigger must be held for the entire dictation.
That is fine for one sentence. It is tiring for a long one, it rules out
dictating while the hands are needed elsewhere, and it ties recording length to
how long a finger can stay on a key. The engine already supports a stop that is
not a key release — `POST /stop` does exactly that through
`stop_and_wait_for_transcription()`. Only the trigger path lacks it.

A second, latent defect makes shipping this unsafe without a fix. The watchdog's
`RECORDING_MAX_S = 300.0` exists as a fault-path backstop, and `_force_recover()`
**discards** `_chunk_texts` (`core/engine.py`). Its guiding comment says it
plainly: *"no push-to-talk hold lasts minutes"*. That assumption dies the moment
recording can outlive a key press. A legitimate five-minute dictation would hit
the backstop and have its already-transcribed text thrown away with no message.
Enabling toggle mode without changing this ships a silent data-loss path.

## What Changes

- **`trigger_mode` config key** — `"hold"` (default, current behavior byte-for-byte)
  or `"toggle"`. In toggle mode a trigger press starts recording and the next
  trigger press stops it; trigger releases no longer stop recording.
- **Toggle semantics live in the engine's trigger worker**, not in the platform
  listeners, so macOS and Linux inherit the behavior from one implementation.
- **Menu surface**: a `Toggle mode` checkbox in Settings, mirroring the existing
  `Copy to clipboard` item. It composes with any trigger rather than doubling the
  Trigger submenu.
- **Two Hyper combo presets**, `⌃⌥⌘E` and `⌃⌥⌘F`. These require combination
  decoding, which does not exist today: a modifier-mask path on macOS and
  modifier tracking on Linux. The Hyper tier (`Control+Option+Command`) is chosen
  because it is the only multi-key tier apps leave unbound by convention — the
  event tap is listen-only and cannot swallow the combination, so a contested
  combination would also fire the frontmost app's own shortcut.
- **Graceful recording limit**: on reaching `RECORDING_MAX_S`, the engine stops
  the recording, drains and assembles the transcribed chunks, places the result
  on the clipboard, and notifies the user — instead of discarding the text.
- **Keycode-table correction** for the letters the new presets name.

## Capabilities

### New Capabilities
<!-- none: this extends existing capabilities -->

### Modified Capabilities

- `event-listener`: gains a trigger-mode concept (press-to-start / press-to-stop
  in addition to hold) and a modifier-combination decode path alongside the
  existing single-key paths. The decoder stays pure and platform-neutral.
- `trigger-selection-ui`: gains a toggle-mode setting and two combination presets;
  the submenu remains single-selection.
- `core-engine`: the watchdog's RECORDING backstop changes from discard-and-recover
  to stop-gracefully-and-preserve; the recovery becomes user-visible.

## Non-Goals

- **Per-trigger language selection.** Investigated and blocked at the library
  level: `onnx-asr` documents `language` as *"only for Whisper and Canary models"*
  (`adapters.py`), and the `<|lang|>` token injection in `models/nemo.py` lives
  only in the encoder-decoder class — the TDT transducer path Whispy uses never
  reads it. Passing a language today is a silent no-op, so a language-labelled
  trigger would assert a forcing that does not happen. The model's own vocabulary
  *does* contain `<|fr|>`, `<|en|>`, `<|predict_lang|>` and `<|nopredict_lang|>`,
  so priming the TDT decoder may be possible; that is a separate spike, and the
  per-trigger-language change is gated on its result. The two combo presets added
  here are deliberately labelled by their keys, not by a language.
- **Multiple simultaneous triggers.** Only justified by per-trigger language;
  deferred with it. `trigger` stays scalar and the submenu stays single-selection.
- **Changing the streaming chunk parameters.** The suspected cause of observed
  language misdetection (short chunks carrying little language evidence) is a
  separate diagnosis with its own measurement.

## Impact

- **Code**: `core/config.py` (new key + validation), `core/engine.py` (toggle
  branch in the trigger worker, graceful watchdog stop), `hardware/event_decode.py`
  (combination parse + decode, keycode-name fixes), `hardware/event_tap.py`
  (combination held-state), `platform/linux/hotkey.py` (modifier tracking),
  `hardware/injection.py` + `platform/linux/injection.py` (clipboard-only
  delivery), `ui/menu_bar.py` and `platform/linux/tray.py` (toggle checkbox).
- **Behavior**: hold mode is unchanged on every path. Toggle mode is opt-in.
- **Tests**: pure decode tests for the combination path; engine tests for the
  toggle branch, the `_fn_pressed` invariant, and the graceful limit.
- **Website**: `website/index.html` must document the toggle mode and the new
  presets in the same change (project convention).
- **No new dependencies.** No API change (`POST /start` and `POST /stop` already
  express both halves of a toggle).

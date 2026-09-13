## Why

Streaming already cuts the recording on pauses and transcribes each chunk while
the user is still speaking, but every chunk's text is held back and typed in one
block when the dictation stops. For a long toggle-mode dictation the user
watches an empty field for the whole time, then gets a wall of text. The audio
work is done live; only the typing is deferred.

A live-typing mode was tried and dropped on the same day in June 2026
(`streaming-incremental-transcription`, tasks 8-9). Every condition that made
it fail has since been removed independently:

| June failure | What caused it | Status today |
| --- | --- | --- |
| garbled fragments | energy-threshold segmenter cut mid-word | WebRTC VAD + `min_speech_s` (`fix-short-chunk-language-drift`) |
| modifier-layer glyphs | trigger key physically held while typing | toggle mode (`add-toggle-dictation-mode`): key released seconds before typing |
| "focus stolen" in full-screen | waveform pill mis-targeted the Space (fixed 2026-06-30 and 2026-07-09) | pill uses `MoveToActiveSpace`; the stop-path `osascript` injection is used daily in full-screen apps without a Space switch |

So the approach was sound and the conditions were not. This change replays it
under the current conditions, scoped to the one trigger mode where it is
physically possible.

## What Changes

- In **toggle mode**, each streaming chunk's cleaned text is typed as soon as it
  is transcribed, instead of accumulating until stop. Text appears roughly one
  second after each pause (`pause_ms` of silence, then the model, then the
  keystrokes). Chunks after the first typed one are prefixed with a space, the
  same join rule the stop-time assembly uses today.
- In **hold (push-to-talk) mode** nothing changes: the trigger key is held for
  the whole recording, and typing under a held modifier mangles every character,
  so chunks keep accumulating and are typed once on release.
- New config key `type_while_speaking` (bool, default **true**), validated and
  migrated like the other streaming keys, applied at runtime, and exposed as a
  "Type while speaking" row in the menu-bar Settings section next to "Toggle
  mode". Setting it to false restores today's type-once-at-stop behaviour in
  toggle mode.
- Text injection becomes **serialized in call order** inside each `TextInjector`
  adapter (macOS `osascript`, Linux `xdotool`): one injection worker, FIFO.
  Today every `inject()` spawns its own thread; with several chunks a few
  seconds apart that is a real interleaving risk (a `max_chunk_s` flush
  followed by a short pause emits two chunks back to back). June solved this
  with a `blocking=True` parameter and reverted it with the mode; this change
  fixes it once, inside the adapter, for every caller.
- The full assembled text of the dictation is still tracked per recording, so
  the recording-limit stop (which copies the transcript to the clipboard rather
  than typing into a field that may have lost focus) and `last_transcription`
  keep their current meaning.
- Website, README config table, `docs/SPECIFICATION.md`, `CHANGELOG.md`
  updated: the feature card that says "text lands as you release the key" gains
  the toggle-mode behaviour, and the menu mockup gains the new row.

**Not in this change (noted for later):** gating typed text on sentence-final
punctuation so only whole sentences appear ("logical block" mode). It is a
strictly additive text buffer on top of this change, and worth doing only if
half-sentences on screen turn out to bother in practice.

## Capabilities

### New Capabilities
<!-- none: this extends the existing streaming pipeline -->

### Modified Capabilities

- `streaming-transcription`: the requirement "Text is typed once on release"
  becomes mode-dependent — per chunk in toggle mode when `type_while_speaking`
  is on, once on release otherwise. The streaming config-key list gains
  `type_while_speaking`. The runtime re-wire requirement covers the new key.
- `text-injection`: new requirement — successive `inject()` calls on one
  adapter SHALL deliver their text in call order, never interleaved.

## Impact

- **Code**: `core/engine.py` (chunk worker types in live mode; per-recording
  live flag; stop path skips the assembled inject when chunks were already
  typed), `core/config.py` (key, default, validation), `hardware/injection.py`
  and `platform/linux/injection.py` (single FIFO injection worker replacing
  per-call threads), `ui/menu_bar.py` (settings row + `update_config` wiring).
- **Behaviour**: toggle-mode users see text arrive during dictation. A focus
  change mid-dictation now scatters text over a wider window than the
  stop-time inject did — same failure class as today, larger surface, documented
  as a known trade-off. A wrong-language chunk (still possible, see
  `fix-short-chunk-language-drift` risks) is typed irreversibly at the pause
  instead of at stop; equally irreversible either way.
- **Tests**: `test_engine.py` (live typing in toggle mode, accumulation kept in
  hold mode, spacing, limit path still copies the whole text, runtime
  re-wire), `test_injection.py` and `test_linux_adapters.py` (FIFO ordering
  under a slow first injection), `test_config_validation.py` (key),
  `test_menu_bar.py` (row), `test_website.py` / `test_docs.py` (sync guards).
- **Docs**: README, `docs/SPECIFICATION.md`, `CHANGELOG.md`, `website/index.html`.
- No new dependencies. No API change (`/status` semantics unchanged).

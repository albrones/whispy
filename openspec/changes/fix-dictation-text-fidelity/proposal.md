## Why

A 178-second toggle-mode dictation with `type_while_speaking` produced text the user had to rewrite by hand. Reading the daemon log for that session (610 chunks) separates the causes, and only one of them is the model:

- **The injected text is corrupted by the keyboard layout.** The model emitted `des tâches, des connaissances...`; the user received `des tqches. des connaissances`. `â` → `q` is exactly the US keycode for `a` landing on a French AZERTY layout (`KeyboardLayout Name = French` on this machine), and every injected `,` arrived as `.`. `copy_to_clipboard` defaults to `False`, so injection goes through `osascript` `keystroke`, which resolves characters to keycodes against the current layout. Characters with a direct AZERTY key (`é`, `à`, `è`, `ç`) survive; dead-key characters (`â`, `ê`, `ô`) and punctuation do not. The user had already dictated this diagnosis into an earlier session without it being recognized as a bug: *"mise à part en fait des points qui devraient être des virgules"*.
- **Long chunks are where the model fails.** Seven chunks in the log came back in English inside a French dictation; their median duration is 12.03 s against 7.0 s for all chunks, and six of the seven are ≥ 8.5 s. Parakeet makes one language decision per call, so a chunk that reaches the `max_chunk_s` ceiling (12 s) bets a lot of audio on a single guess. Chunks closed by a real pause are almost always right.
- **Audio is lost without a trace.** 32 chunks cleared the RMS gate *and* the voiced-duration gate, reached the model, and came back empty — 180 seconds of real speech, 24 of those chunks longer than 3 s, the longest 16.7 s. The user's own opening sentence in the session that prompted this analysis is one of them (`Model returned no text for a 12.48s clip`). It is logged at INFO, never retried, and never surfaced.
- **Every chunk is punctuated as a standalone sentence.** Chunks are joined with a bare space, so a sentence cut by the length ceiling reads `...des tickets.` `Des tickets qui se baladent...` — a false sentence break plus a false capital, at every force-flush boundary.

## What Changes

- Default `copy_to_clipboard` to `True` on both platforms, making clipboard-paste the delivery path. Pasting hands the text over as data and never resolves it against a keyboard layout, so accents and punctuation arrive intact. Keystroke mode stays available as an explicit opt-out, documented as US-layout-only. **BREAKING** for users who relied on the keystroke default: dictation now briefly takes over the clipboard (snapshot and restore already exist).
- Lower the `max_chunk_s` default from 12 s to 8 s, keeping the existing soft-gap and hard-cap rules unchanged, and record the measured language-drift rationale in the spec.
- Retry a chunk once on the untrimmed clip when the model returns empty text for a clip that passed both non-speech gates, and log the remaining losses at WARNING with the measurements that would explain them, instead of discarding at INFO.
- Make chunk joining aware of *why* the previous chunk closed: a chunk force-flushed by the length ceiling (or closed by a short pause) is a continuation, so its trailing sentence period is withheld and the next chunk is joined as a continuation rather than as a new sentence. A chunk closed by a genuine pause keeps its punctuation and capitalization as today.
- Update the website and the config documentation for the changed `copy_to_clipboard` default.

## Capabilities

### New Capabilities

_None — every behaviour changed here belongs to an existing capability._

### Modified Capabilities

- `text-injection`: injection SHALL deliver text byte-exact regardless of the active keyboard layout; keystroke mode SHALL be documented as correct only on a US layout.
- `core-engine`: the `copy_to_clipboard` default flips from `False` to `True`.
- `streaming-transcription`: the `max_chunk_s` default becomes 8 s with a measured rationale; chunk joining becomes continuation-aware instead of always inserting a bare space.
- `audio-capture`: an empty model result on a clip that cleared both non-speech gates SHALL be retried untrimmed once and, if still empty, reported as a loss rather than a routine discard.

## Impact

- `src/whispy/core/config.py` — `DEFAULT_CONFIG["copy_to_clipboard"]`, `DEFAULT_CONFIG["max_chunk_s"]`.
- `src/whispy/core/segmentation.py` — `SpeechSegmenter.feed` must report *why* a boundary occurred, not just that one did.
- `src/whispy/core/audio.py` — chunk emission carries the boundary reason; `transcribe` gains the untrimmed retry and the loss-level log.
- `src/whispy/core/engine.py` — `_transcribe_and_inject_chunk` and the stop-time assembly apply the continuation join rule.
- `website/index.html` — the menu-bar mockup's "Copy to clipboard" row and any text describing the default.
- `docs/` config reference — the `copy_to_clipboard` and `max_chunk_s` rows.
- Tests: `tests/test_injection.py`, `tests/test_config_validation.py`, `tests/test_segmentation.py`, `tests/test_audio.py`, `tests/test_engine.py`, `tests/test_website.py`.
- No new dependency. No API change to the HTTP server.

## Context

See `proposal.md` — Why for the measurements. The constraints that shape the approach:

- **macOS injection cannot use `CGEventPost` directly.** `src/whispy/hardware/injection.py` routes everything through `osascript` → System Events precisely because System Events is Apple-signed and a self-signed Whispy's own `CGEventPost` is dropped. `CGEventKeyboardSetUnicodeString` — the one API that types arbitrary text without touching the layout — is therefore unavailable. System Events exposes `keystroke` (layout-resolved) and `key code` (raw positions); neither can deliver a Unicode string.
- **Typing is append-only.** In toggle mode with `type_while_speaking`, a chunk's text is in the user's field microseconds after it is transcribed. Nothing already typed can be revised, so any join rule has to be decided *before* the text is delivered, not after.
- **A saved config carries every known key.** `save_config` (`config.py:304`) writes the full `DEFAULT_CONFIG` key set, so every existing install already has `copy_to_clipboard: false` and `max_chunk_s: 12.0` on disk. Changing a default alone reaches no existing user, including the one who reported this.
- **The segmenter already knows everything needed for the join rule** — it tracks `_silence_s` and `_buffered_s` per frame — but `feed()` collapses it all into a `bool`.

## Goals / Non-Goals

**Goals:**

- Deliver the transcript to the field byte-exact, whatever the user's keyboard layout.
- Keep the chunk ceiling inside the range where the model's per-call language decision is reliable.
- Make chunks the model silently swallows visible and recoverable.
- Stop a chunk boundary from reading as a sentence boundary when it was not one.

**Non-Goals:**

- Cross-chunk decoder context. The transducer has none; nothing here changes that.
- Forcing a language. `onnx_asr` accepts `language=` only for Whisper and Canary; Parakeet TDT detects per call and there is no biasing channel.
- Repairing layout-corrupted text after the fact, or carrying a per-layout character table.
- Re-transcribing the whole recording at stop to replace the streamed text. It would fix punctuation globally but doubles the compute and makes the typed text jump under the user's cursor.
- Retuning `pause_ms`, `min_speech_s`, or the RMS/VAD gate thresholds. Those are measured elsewhere and are not implicated by this session's data.

## Decisions

### D1 — Clipboard paste becomes the default delivery path

The corruption is `osascript`'s `keystroke` resolving characters against the active layout. Alternatives:

| Option | Verdict |
|---|---|
| `CGEventKeyboardSetUnicodeString` + `CGEventPost` | Correct in principle, unavailable in practice — the repo already records that a self-signed Whispy's `CGEventPost` is dropped. Revisiting it needs a re-measurement, not a guess. |
| Per-layout character → `key code` table | Would have to cover every layout macOS ships, including dead-key sequences. Large, permanently incomplete, and wrong silently. |
| Detect the active layout at startup and force clipboard when it is not US | Only moves the decision; still needs the clipboard path to exist and be correct, and adds a layout-reading dependency plus a live-switch failure mode. |
| **Flip `copy_to_clipboard` to `True`** | The clipboard path already exists, already snapshots and restores, already forces UTF-8 on every helper, and already detects the `1002` denial. One default plus a migration. |

Keystroke mode stays as an explicit opt-out for anyone on a US layout who prefers it, and gets documented as US-only.

### D2 — `max_chunk_s` 12 → 8, and nothing else in the segmenter's rules

The soft-gap and hard-cap mechanics stay exactly as they are; only the ceiling moves. The hard cap follows it automatically (`max_chunk_s * 1.5`: 18 s → 12 s), which is the change that matters most — the worst drifted chunk in the log was 14.19 s, reachable under the old hard cap and not under the new one.

Rejected: making the ceiling adaptive on a running language estimate. It would need a language detector the system does not have, to fix a failure that a constant already bounds.

The ceiling only affects chunks that never got a pause. The short-chunk floor (`min_speech_s`, the lone-word rule) is untouched, so this cannot push chunks back into the *other* documented drift regime — short isolated chunks resolving into the wrong language.

### D3 — `feed()` reports a boundary reason, not a bool

`SpeechSegmenter.feed()` returns the reason a boundary occurred (or nothing). Two classes are enough for the join rule:

- **sentence** — closed by silence at or above a sentence-break threshold (default: `pause_ms`, i.e. today's boundary), and the tail flush at stop.
- **continuation** — the `max_chunk_s` soft gap, the hard cap, and any qualifying pause below the sentence-break threshold.

The lone-word 2 s emission (`LONE_WORD_PAUSE_S`) is a **sentence** break, not a
continuation: it fires on silence of 2 s, which is far above any sensible
sentence-break threshold, so classifying it as a continuation would contradict
the rule in the line above and glue a word the speaker clearly finished onto the
next utterance with a comma. (An earlier draft of this document listed it under
continuation; `tasks.md` 3.2 and the streaming-transcription delta both say
sentence, and that is what ships.)

The threshold is a separate knob from `pause_ms` so that raising `pause_ms` later cannot silently reclassify boundaries. Defaulting it *to* `pause_ms` means today's behaviour is the starting point: every pause boundary is a sentence break, every forced cut is a continuation. That is the split the log data supports; a stricter threshold is a tuning question, not a design one.

The reason travels with the chunk: `AudioEngine`'s chunk sink gains the reason alongside the path, and the engine's chunk worker carries it to the join.

### D4 — Withhold the trailing period, prepend the separator

The join cannot rewrite text already typed, so the period is the thing that must wait. For each chunk:

1. Strip a trailing `.` before delivering the chunk's text (never `?` or `!` — a wrongly kept `?` is fixable by eye, a wrongly dropped one is not).
2. Deliver the *previous* boundary's separator as this chunk's prefix: `" "` after a sentence boundary, `", "` after a continuation, nothing for the first chunk of the recording.
3. After a continuation, lower the first character — unless the first token is all-caps or matches a configured `custom_vocabulary` term. Both exceptions reuse data the system already has.
4. The final chunk of a recording restores its period, since no boundary follows it.

Same function serves the live path and the stop-time assembly, so the two cannot drift apart — the current bug where they both hardcode `" "` is what makes that worth stating.

Known ceiling: a proper noun that is neither all-caps nor in the vocabulary gets lowered at a continuation boundary. A wrong lower-case letter is a smaller defect than a false sentence break, and the vocabulary escape hatch is the documented fix.

### D5 — One untrimmed retry, then a loss warning

Trimming is the only transformation between the gates and the model call, and the empty results in the log skew toward long clips — exactly the ones that get trimmed. So: if the model returns empty for a trimmed copy, call once more with the original. One retry, not a loop: the cost is bounded and a second empty answer is information, not a reason to keep trying.

Rejected: loosening a gate. The gates are what keep `Yeah.` and `Thank you.` out of the user's field, and these clips *passed* them — the loss is downstream of every gate.

The warning carries duration, peak RMS and voiced seconds so the next investigation starts with numbers instead of a re-drive.

### D6 — Version-gated one-time config migration

`CONFIG_VERSION` 1 → 2, with a v1→v2 step in `_migrate_config`:

- `copy_to_clipboard` → `True`, unconditionally.
- `max_chunk_s` → new default, but only when it still equals `12.0`.

The asymmetry is deliberate. `max_chunk_s: 12.0` on disk is indistinguishable from the old default, and a user who tuned it to something else clearly meant it — so an untouched value is migrated and a tuned one is left alone. `copy_to_clipboard: false` is equally indistinguishable, but leaving it means shipping the fix to nobody while the mode it preserves silently corrupts text; the setting stays one menu click away.

### D7 — The soft-flush gap becomes a config key, defaulting to 350 ms

D2 lowered `max_chunk_s` and deliberately left the soft-gap mechanics alone. A
live drive showed why that was incomplete: with the ceiling at 8 s the soft gap
fires on every long sentence, and a 200 ms gap is short enough to occur *inside*
speech. Measured on a live French dictation at `vad_aggressiveness: 3`, the
ceiling cut *Régie* in half — `...je suis dans Rég.` then `la version app`, the
final syllable gone. The join rule cannot repair that: a lost syllable is lost.

| Option | Verdict |
|---|---|
| Revert `max_chunk_s` to 12 s | Trades the language-drift fix straight back for the cut frequency. The drifted chunks in the original log had a median of 12.03 s — this is the exact regime being reverted into. |
| Raise `SOFT_FLUSH_GAP_S` as a constant | Correct mechanism, but the number comes from one speaker at one VAD aggressiveness, and a constant makes retuning a rebuild. |
| **`soft_gap_ms` config key, default 350** | Same mechanism, retunable without a rebuild. Follows the precedent `min_speech_s` set: a threshold measured on one voice is a key, not a constant. |

Known ceiling: a higher gap threshold routes more run-on speech to the
unconditional hard cap, which cuts at an arbitrary frame and so can itself land
mid-word. The hard cap is reached only by speech with no qualifying gap for half
again the ceiling, against a soft gap that was firing on every long sentence —
so the trade moves the defect from common to rare rather than removing it. If
the hard cap becomes the visible failure, the next move is to make *it* seek a
gap rather than to lower the threshold again.

### D8 — A migration backs up the file it replaces

A migration is the only moment the engine rewrites a config file it did not
write. When settings turned up at their defaults after an upgrade, there was no
pre-migration file to compare against and no log line naming what changed, so
the cause could not be established from what remained on disk — which is its own
kind of failure, independent of whether the migration was at fault.

So: copy `config.json` to `config.json.v<previous>.bak` before persisting, and
log the keys the migration changed. Named for the source version rather than
timestamped, so the file is bounded (one per version crossed) and self-
describing. A backup that cannot be written is logged and does not block the
migration: refusing to start over a failed backup is worse than the loss it
guards against.

Rejected: backing up on every `save_config`. Saves happen on every settings
change and the file would churn for no diagnostic value — the migration is the
one write the user did not ask for.

## Risks / Trade-offs

- **Clipboard churn during live typing.** A 3-minute dictation at the new ceiling is ~25 chunks, each doing snapshot → copy → `Cmd+V` → restore. If the user copies something mid-dictation, the next restore overwrites it. → Accepted: the snapshot/restore pair already exists and is specced; the window is one chunk wide. A future refinement is to snapshot once per recording rather than per chunk — out of scope here, and noted as a follow-up.
- **Paste latency per chunk.** The restore step already sleeps `_CLIPBOARD_RESTORE_DELAY` (0.15 s) and runs on the shared FIFO injector thread, so live typing gains ~0.15 s of serialized work per chunk. → Injection is already off the capture and transcription threads, and the queue preserves order; the user sees text arrive slightly later, never out of order.
- **`Cmd+V` is not paste everywhere.** A target app with a non-standard paste binding gets nothing where keystrokes would have typed something. → Keystroke mode remains available and documented; the `1002` detection already surfaces the denial case.
- **More chunks means more model calls.** 12 s → 8 s raises the call count on run-on speech by roughly half. → Per-chunk cost is already specced as proportional to audio duration, not a fixed floor, so total compute is roughly unchanged; only the per-call overhead multiplies.
- **A retry doubles latency on the clips that fail.** → Bounded to one extra call, and only on clips that already produced nothing.
- **Lower-casing at a continuation boundary can hit a proper noun.** → Covered in D4; all-caps and vocabulary terms are exempt, the rest is a visible, one-character defect.
- **Migration overrides a deliberate keystroke choice once.** → Covered in D6; stated in the changelog and the docs row.

## Migration Plan

1. Ship the new defaults and the v1→v2 migration together — a default without the migration is a no-op for every existing install.
2. On first launch after the upgrade, `load_config` runs the migration and rewrites `config.json`. No user action.
3. Rollback: reverting the code leaves `_version: 2` and `copy_to_clipboard: true` on disk. Harmless — the old build reads both keys and honours the saved values — but the setting does not revert itself. Say so in the release notes.

## Context

Whispy transcribes speech via faster-whisper and injects text into the focused field. A `custom_vocabulary` config feeds `initial_prompt` to bias the model, but it's manual and static. The `hotwords` parameter exists in faster-whisper but is unused. No post-transcription correction mechanism exists beyond credit stripping.

The transcription pipeline today:
```
Audio → faster-whisper(initial_prompt=vocab) → strip_credit → clean_text → inject via osascript
```

Injection is write-only — Whispy never reads the focused text field. macOS Accessibility permission is already granted (required for `osascript` keystroke injection).

## Goals / Non-Goals

**Goals:**
- Zero-effort learning: detect user corrections automatically, no explicit action required
- Persistent correction memory across sessions
- Two-layer correction: bias the model (hotwords) + fix output (post-processing)
- Graduated confidence: require repeated corrections before auto-replacing

**Non-Goals:**
- Real-time text field observation (AXObserver) — too complex for v1, approach B deferred
- Learning from corrections across different apps/fields — only same-field-same-session
- Phonetic similarity matching — simple exact-match diffing only
- Case-sensitive corrections — case-insensitive matching for v1
- Multi-word expression rewriting ("open AI" → "OpenAI") — single word corrections only for v1
- Custom vocabulary subsumption — corrections store is separate from existing `custom_vocabulary`

## Decisions

### 1. Detection: snapshot-diff on next Fn press

**Choice:** After injection, snapshot the focused element and field value via `AXUIElementCopyAttributeValue`. On next Fn press (before recording starts), re-read the same element and diff the injected region.

**Why over AXObserver (real-time):** AXObserver fires per keystroke, requires debouncing, threading, lifecycle management, and breaks on Electron/web apps that don't emit `AXValueChanged`. Snapshot-diff is one read on inject, one read on next Fn press — two calls total.

**Why over explicit correction UI:** User asked for zero-effort. A correction hotkey/menu adds friction. Snapshot-diff is invisible.

**Limitation:** Misses corrections when user leaves the field before next dictation. Acceptable — dictation happens in bursts in the same field.

### 2. AX text field reading

**Choice:** Use `AXUIElementCopySystemWideElement()` → `kAXFocusedUIElementAttribute` → `kAXValueAttribute` to read the focused text field content.

**Implementation:** New module `src/whispy/hardware/ax_reader.py` — two functions:
- `snapshot_focused_field() → FieldSnapshot | None` — returns `{element_ref, app_pid, value, timestamp}`
- `read_focused_field() → str | None` — returns current AXValue or None

**Dependency:** `pyobjc-framework-ApplicationServices` already installed. `AXUIElementCopyAttributeValue` is in `ApplicationServices.HIServices`, no new dependency needed. Verify at implementation time.

### 3. Diffing: simple substring region

**Choice:** Store the injected text and its start offset in the field. On diff, extract the same region from the current field value and compare character-by-character. Only word-level changes within the injected region count as corrections.

**Algorithm:**
```
injected = "wispy is great"
snapshot_value = "Hello wispy is great"
inject_offset = 6

# On next Fn press:
current_value = "Hello Whispy is great"
current_region = current_value[6:6+len(injected)]  # may differ in length

# Word-level diff:
old_words = injected.split()     # ["wispy", "is", "great"]
new_words = current_region.split()  # ["Whispy", "is", "great"]
corrections = {old: new for old, new in zip(old_words, new_words)
               if old.lower() != new.lower()}
# → {"wispy": "Whispy"}
```

**Why not fuzzy matching:** Added complexity, false positives. Simple word-by-word comparison catches the target case (single word spelling corrections). Insertions/deletions within the region are ignored for v1.

### 4. Correction store format

**Choice:** `~/.config/whispy/corrections.json`, loaded on startup, saved atomically (same pattern as `config.json`).

```json
{
  "version": 1,
  "corrections": {
    "wispy": {
      "replacement": "Whispy",
      "occurrences": 12,
      "corrections_count": 5,
      "first_seen": "2026-07-15",
      "last_corrected": "2026-07-15"
    }
  }
}
```

Key is lowercase wrong word. `occurrences` = times the wrong word appeared in transcriptions. `corrections_count` = times the user actually fixed it.

### 5. Activation thresholds

**Choice:** Two tiers:
- **Hotwords** (bias the model): added after first correction (`corrections_count >= 1`)
- **Auto-replace** (post-processing): activated after 3 corrections (`corrections_count >= 3`)

**Why 3:** Balances between learning fast and avoiding false positives from accidental edits. One correction could be coincidence; three is a pattern.

### 6. Hotwords wiring

**Choice:** Pass correction store entries as `hotwords` param to `model.transcribe()`, separate from existing `initial_prompt` (which carries `custom_vocabulary`).

**Why separate:** `hotwords` and `initial_prompt` serve different purposes and have independent token budgets. `hotwords` is more targeted for vocabulary biasing. Keeping them separate avoids token budget conflicts with `condition_on_previous_text`.

### 7. Post-transcription replacement

**Choice:** New step in the text processing pipeline, after `clean_text()` and before `inject()`. Case-insensitive whole-word replacement using `re.sub(r'\b' + re.escape(word) + r'\b', replacement, text, flags=re.IGNORECASE)`.

**Pipeline becomes:**
```
Audio → faster-whisper(hotwords=learned_vocab) → strip_credit → clean_text → apply_corrections → inject
```

### 8. Streaming mode handling

**Choice:** In streaming mode, chunks inject incrementally. Snapshot only on the **final chunk** (when recording stops and all chunks are aggregated). The snapshot stores the full aggregated text, not individual chunks.

### 9. Menu bar UI

**Choice:** Add a "Learned Words" submenu showing correction entries with their status (learning/active). Items are clickable to remove. No edit UI — remove and let re-learning happen.

## Risks / Trade-offs

- **[AX reading fails on some apps]** → Some applications don't expose `AXValue` (e.g., some Terminal emulators, games). Mitigation: `snapshot_focused_field()` returns `None` on failure, detection silently skips. No crash, no degradation.
- **[False positive corrections]** → User edits text in the injected region for reasons unrelated to transcription errors. Mitigation: threshold of 3 before auto-replace activates. Single false edits don't trigger permanent corrections.
- **[Offset drift]** → If user types before the injected region between injection and next Fn press, the offset shifts. Mitigation: search for the injected text in the field value as fallback if region extraction doesn't match, within a ±50 character window around the stored offset.
- **[Token budget overflow]** → Too many corrections in hotwords exceeds ~224 token limit. Mitigation: sort by `corrections_count` descending, take top N that fit within budget. Least-corrected entries drop first.
- **[Stale corrections]** → User's vocabulary changes over time. Mitigation: could add decay in v2 (not in scope). For now, manual removal via menu bar.

## Open Questions

- Should corrections be backed up / exportable? (Probably not for v1)
- Should the correction store merge with or replace `custom_vocabulary` long-term?

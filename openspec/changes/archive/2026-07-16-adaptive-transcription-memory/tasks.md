## 1. AX Text Field Reader

- [x] 1.1 Create `src/whispy/hardware/ax_reader.py` with `snapshot_focused_field()` and `read_focused_field()` using AXUIElement APIs (ApplicationServices). Return `FieldSnapshot` dataclass or `None` on failure.
- [x] 1.2 Unit test: mock AX calls, verify snapshot returns correct structure and None on inaccessible fields.

## 2. Correction Store

- [x] 2.1 Create `src/whispy/core/corrections.py` with `CorrectionStore` class: load/save `~/.config/whispy/corrections.json`, atomic writes, add/remove/query corrections, occurrence tracking.
- [x] 2.2 Unit test: store CRUD, corrupt file handling, empty file creation, atomic save.

## 3. Snapshot-Diff Engine

- [x] 3.1 Add snapshot logic to `engine.py`: after injection, call `snapshot_focused_field()` and store result. In streaming mode, snapshot only after final chunk.
- [x] 3.2 Add diff logic to `engine.py`: on Fn press (before recording), call `read_focused_field()`, compare injected region word-by-word, extract corrections. Handle offset drift with ±50 char search fallback.
- [x] 3.3 Wire detected corrections into `CorrectionStore.add_correction()`.
- [x] 3.4 Unit test: diff extraction with unchanged text, single word correction, offset drift, field switch (skip).

## 4. Hotwords Integration

- [x] 4.1 Add `hotwords` param passthrough in `AudioEngine.transcribe()` (audio.py).
- [x] 4.2 Build hotwords string from `CorrectionStore` in engine.py (all entries with corrections_count >= 1, sorted by count desc, truncated to token budget).
- [x] 4.3 Pass hotwords alongside existing initial_prompt at all transcribe call sites in engine.py.
- [x] 4.4 Unit test: hotwords string building, token budget truncation, coexistence with custom_vocabulary.

## 5. Post-Transcription Replacement

- [x] 5.1 Add `apply_corrections(text, store)` function in `corrections.py`: case-insensitive whole-word replacement for entries with corrections_count >= 3.
- [x] 5.2 Wire `apply_corrections()` into engine.py pipeline between `clean_text()` and `inject()` at all transcribe-and-inject paths.
- [x] 5.3 Track occurrences: when a known wrong word appears in transcription output, increment `occurrences` in store.
- [x] 5.4 Unit test: word boundary matching, case-insensitive replacement, threshold gating, occurrence counting.

## 6. Menu Bar UI

- [x] 6.1 Add "Learned Words" submenu in `menu_app.py` showing correction entries with status (learning: count < 3, active: count >= 3). Click to remove.
- [x] 6.2 Manual test: verify submenu populates, entries removable, empty state.

## 7. Integration & Website

- [x] 7.1 End-to-end test: inject text, simulate field edit, trigger diff, verify correction stored and applied on next transcription.
- [x] 7.2 Update `website/index.html` feature cards to mention adaptive vocabulary / learning from corrections.

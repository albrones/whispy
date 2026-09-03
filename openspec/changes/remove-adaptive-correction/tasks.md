## 1. Preserve knowledge (before deletion)

- [x] 1.1 Create the GitHub issue via `gh issue create`: title like "Reimplement adaptive correction learning with robust alignment". Body: implementation state as of `b18c8c6` (files: `src/whispy/core/corrections.py`, `src/whispy/hardware/ax_reader.py`, engine/menu hooks, `tests/test_corrections.py`), why it was gated off (fixed-window alignment mislearned word→word shifts from continued dictation, fed them back as Whisper hotwords — self-reinforcing hallucination, see `FEATURE_MATRIX.md:75`), acceptance criterion (rewritten alignment before any re-enable), and note that this change deletes the code — `git show b18c8c6` is the reference.
- [x] 1.2 Record the issue URL in this change's design.md (Open Questions → resolved) for the PR description.

## 2. Delete the feature code

- [x] 2.1 Grep for importers of `whispy.core.corrections` and `whispy.hardware.ax_reader` outside the feature itself; confirm only engine/menu/tests reference them.
- [x] 2.2 Delete `src/whispy/core/corrections.py` and `src/whispy/hardware/ax_reader.py`.
- [x] 2.3 `src/whispy/core/engine.py`: remove the corrections import (`:34`), correction-store init (`:261-262`), `hotwords=self._build_hotwords()` and `_build_hotwords` (`:540`), `_detect_corrections` (`:572+`), the correction-detection step in the trigger-worker press path, and any `apply_corrections` call in the cleaning pipeline.
- [x] 2.4 `src/whispy/ui/menu_bar.py`: remove the "Learned Words" submenu and `_rebuild_learned_menu` (`:203-204`, `:470-490`).
- [x] 2.5 Check `src/whispy/core/audio.py` for correction/hotwords references and clean if any.

## 3. Update tests

- [x] 3.1 Delete `tests/test_corrections.py`.
- [x] 3.2 `tests/test_engine.py`: remove `TestCorrectionDetection` and `TestAdaptiveLearningDisabledByDefault`; update worker call-order assertions (press order becomes: notify pressed → cue → `start_recording()`).
- [x] 3.3 `tests/test_docs.py`: drop references to `tests/test_corrections.py` / adaptive rows.
- [x] 3.4 Run the full suite: `./.venv/bin/pytest` — green.

## 4. Sync docs and installer

- [x] 4.1 `README.md:13`: remove the "Learns your words" bullet (optionally replace with one line pointing at the tracking issue).
- [x] 4.2 `FEATURE_MATRIX.md:75`: remove the adaptive-vocabulary row (or convert it to a "removed, tracked in issue #N" note if the matrix has such a convention — prefer removal).
- [x] 4.3 `install.sh:181`: change the Debian/Ubuntu hint to `sudo apt install xdotool xclip libportaudio2` (align with README:96 and the website; sounddevice needs the system PortAudio runtime on Linux).
- [x] 4.4 Grep `CLAUDE.md` / other docs for "learns your words" / adaptive-correction claims and remove them (CLAUDE.md memory notes about the poison loop may stay — they explain history, not advertise the feature).

## 5. Sync the website

- [x] 5.1 `website/index.html`: remove the "Learns your words" feature card (rebalance the feature-card grid if the layout needs an even count).
- [x] 5.2 `website/index.html`: add a "Trigger" entry to the animated menu-bar demo dropdown (alongside Model and Language, matching `menu_bar.py:175-225`); confirm no "Learned Words" entry is depicted anywhere.
- [x] 5.3 Eyeball the demo animation locally (open `website/index.html`) — dropdown timing/height still correct after the row change.

## 6. Guard and verify

- [x] 6.1 Extend `tests/test_website.py`: assert the page contains no adaptive-learning claim (case-insensitive check for "learns your words" / "remembers" in feature copy) and that the demo dropdown markup includes "Trigger" and excludes "Learned Words".
- [x] 6.2 Run `./.venv/bin/pytest tests/test_website.py tests/test_docs.py` — green.
- [x] 6.3 Run the full suite once more — green; then `graphify update .` to refresh the knowledge graph.

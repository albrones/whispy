## 1. Marshal status updates to the main thread (menu_bar.py)

- [ ] 1.1 Wrap `update_status_display` so AppKit mutation runs on the main thread (mirror `WaveformWindow`'s `callAfter`/`isMainThread` guard)

## 2. Remove dead IndicatorWindow (menu_bar.py + indicator_window.py)

- [ ] 2.1 Remove `IndicatorWindow` allocation and the off-main-thread `hide()` calls
- [ ] 2.2 Delete `indicator_window.py` (or, if kept, route show/hide through the main thread and guard empty `screens()`)

## 3. Remove unused AudioLevelMonitor (audio_level.py)

- [ ] 3.1 Remove `AudioLevelMonitor` and any references; confirm the live waveform still uses `engine.get_level`

## 4. Tests

- [ ] 4.1 Assert status/UI callbacks marshal to the main thread (not just present as source strings)
- [ ] 4.2 Update tests that referenced the removed dead code

## 5. Verification

- [ ] 5.1 Run the full test suite; confirm no regression
- [ ] 5.2 `ruff check` / `ruff format --check` on changed files
- [ ] 5.3 `openspec validate fix-ui-main-thread-safety --strict`

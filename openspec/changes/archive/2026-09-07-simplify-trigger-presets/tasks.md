## 1. Remove the presets

- [x] 1.1 Drop `("⌃⌥⌘E", "ctrl+alt+cmd+e")` and `("⌃⌥⌘F", "ctrl+alt+cmd+f")` from `TRIGGER_PRESETS` in `src/whispy/core/config.py`; rewrite the header comment to say combination strings remain valid config values (decoder kept) but are not offered as presets; verify `./.venv/bin/pytest tests/test_config_validation.py` passes
- [x] 1.2 In `tests/test_menu_bar.py`, retarget the combo-select test (currently `⌃⌥⌘E` / `"ctrl+alt+cmd+e"`) to a single-key preset (e.g. F13 / 105) so "selection persists and re-checks" stays covered, and add an assertion that no `TRIGGER_PRESETS` value is a string; verify `./.venv/bin/pytest tests/test_menu_bar.py` passes
- [x] 1.3 Add a menu test for the kept behaviour: with `trigger` set to `"ctrl+alt+cmd+e"`, the submenu title reads `Trigger: ctrl+alt+cmd+e` and no item is checked; verify it passes

## 2. Website and docs

- [x] 2.1 Remove `<kbd>⌃⌥⌘E</kbd>` and `<kbd>⌃⌥⌘F</kbd>` from the trigger list in `website/index.html` (demo lede, ~line 107); verify `./.venv/bin/pytest tests/test_website.py` passes
- [x] 2.2 `grep -rn "⌃⌥⌘" --include=*.md --include=*.html --include=*.py .` (excluding `openspec/changes/`) returns no hit outside decoder tests; verify by running the grep

## 3. Verification

- [x] 3.1 Full `./.venv/bin/pytest` and `./.venv/bin/ruff check .` green
- [x] 3.2 Build with `make app`, relaunch, open the Trigger submenu: four items, Fn checked by default; select F13 and confirm the title updates without Restart
- [x] 3.3 Before archiving, confirm `add-toggle-dictation-mode` is archived so this delta applies on top of its `Trigger selection submenu` text

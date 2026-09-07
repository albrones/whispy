## Why

In clipboard mode, every accented character dictated in French comes out
mangled: « là créer ça » is typed as « l√† cr√©er √ßa ». The model output is
correct; the corruption happens in the hand-off to the clipboard. `pbcopy` and
`pbpaste` decode their stream through the process locale, and `Whispy.app`
launched by launchd or Finder has no `LANG`/`LC_*` set, so both fall back to
Mac Roman. UTF-8 `ç` (`C3 A7`) is stored as the two Mac Roman glyphs `√ß`.
Reproduced in one line: `printf 'ça' | env -i pbcopy; pbpaste` → `√ßa`; with
`LC_ALL=en_US.UTF-8` → `ça`. The keystroke path (`osascript` argv) is unaffected.
This is the bug behind the recent "language detection" suspicion.

## What Changes

- The macOS injector runs every clipboard helper (`pbcopy` for copy, paste and
  copy-only; `pbpaste` for the pre-dictation snapshot) with a UTF-8 locale
  forced in the child environment, so text round-trips byte-exact regardless
  of how the app was launched.
- Snapshot and restore share that environment: fixing only `pbcopy` would
  restore a Mac Roman snapshot through a UTF-8 `pbcopy` and corrupt the user's
  previous clipboard instead.
- No config, no UI, no website change: this is a correctness fix to existing
  behaviour.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities

- `text-injection`: gains an explicit requirement that clipboard-mode delivery
  and clipboard snapshot/restore preserve non-ASCII text exactly, independent
  of the launch environment's locale.

## Impact

- **Code**: `src/whispy/hardware/injection.py` (`_spawn` Popen, `_snapshot_clipboard` run).
- **Tests**: `tests/test_injection.py` asserts the child environment on every
  clipboard helper call.
- **Untouched**: Linux injector (`xdotool`/`xclip`), not measured, not in scope.
- **No new dependencies.**

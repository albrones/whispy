## 1. Force a UTF-8 locale on the clipboard helpers

- [x] 1.1 In `src/whispy/hardware/injection.py`, add a module-level env dict (`{**os.environ, "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}`) and pass it as `env=` to the `Popen` in `_spawn`; verify existing `./.venv/bin/pytest tests/test_injection.py` still passes
- [x] 1.2 Pass the same `env=` to the `subprocess.run(["pbpaste"], ...)` in `_snapshot_clipboard`; verify `tests/test_injection.py` still passes

## 2. Tests

- [x] 2.1 In `tests/test_injection.py`, assert that every `Popen` call recorded for the clipboard path, the keystroke path and `copy_only` carries `env["LC_ALL"] == "en_US.UTF-8"`; verify the new assertions fail when the `env=` argument is removed and pass with it
- [x] 2.2 Assert the `pbpaste` snapshot `run` call carries the same `env`; verify it passes
- [x] 2.3 Add a pure round-trip test on this Mac only (skip elsewhere): `printf 'là créer ça' | env -i LC_ALL=en_US.UTF-8 pbcopy` then `env -i LC_ALL=en_US.UTF-8 pbpaste` returns the same bytes, snapshotting and restoring the developer clipboard around it; mark it `macos-real` tier; verify it passes locally

## 3. Real-seam verification

- [x] 3.1 `make app`, relaunch `Whispy.app` from Finder (no shell env), set `copy_to_clipboard: true`, dictate « là créer ça » into a text field; verify the typed text is exact, no `√`
- [x] 3.2 Put « déjà vu » on the clipboard, dictate once in clipboard mode, paste again; verify the clipboard was restored to « déjà vu » intact
- [x] 3.3 Full `./.venv/bin/pytest` and `./.venv/bin/ruff check .` green

## 1. Config file and directory permissions (`src/whispy/core/config.py`)

- [x] 1.1 In `save_config`, after `config_dir.mkdir(parents=True, exist_ok=True)`, `chmod` `config_dir` to `0700`, wrapped in `try/except OSError` (log a warning on failure, do not abort the save).
- [x] 1.2 After writing `tmp_path` and before `os.replace(tmp_path, config_path)`, `chmod` `tmp_path` to `0600`, wrapped in `try/except OSError` (log a warning on failure, still proceed with `os.replace` — a save with default perms is better than no save).
- [x] 1.3 Unit test: call `save_config` on a fresh (non-existent) config dir/file and assert `config.json` has mode `0600` and its parent directory has mode `0700`.
- [x] 1.4 Unit test: pre-create `config.json` with `0644` (`os.chmod`), call `save_config` again, and assert the file ends up at `0600` (self-healing on next save, no migration step).
- [x] 1.5 Unit test: monkeypatch `os.chmod` to raise `OSError` and assert `save_config` still completes (file content written, no exception propagates).

## 2. Corrections file and directory permissions (`src/whispy/core/corrections.py`)

- [x] 2.1 In `_save`, after `self._path.parent.mkdir(parents=True, exist_ok=True)`, `chmod` the parent directory to `0700`, wrapped in `try/except OSError` (log a warning, do not abort the save).
- [x] 2.2 Verify `tempfile.mkstemp(dir=..., suffix=".tmp")` already creates the temp file at `0600` on this platform (it does, by stdlib default) — no code change needed for the temp file itself, but add a comment noting this is relied upon so a future refactor (e.g. switching to `open()`) doesn't silently regress it.
- [x] 2.3 Rewrite `_save`'s write/replace logic as a plain `try/finally` for the fd (`os.write` then `finally: os.close(fd)`), followed by a separate `try: os.replace(tmp, self._path) except Exception: os.unlink(tmp); raise` — removing the `except BaseException` / `os.get_inheritable(fd)` pattern entirely.
- [x] 2.4 Unit test: call `_save` (via `add_correction`) on a fresh store and assert `corrections.json` has mode `0600` and its parent directory has mode `0700`.
- [x] 2.5 Unit test: pre-create `corrections.json` with `0644`, trigger a save, and assert it ends up at `0600`.
- [x] 2.6 Unit test: monkeypatch `os.replace` to raise `OSError` during `_save` and assert (a) the original `OSError` propagates unchanged (not masked by a secondary error), and (b) the `.tmp` file no longer exists on disk after the call.
- [x] 2.7 Unit test: monkeypatch `os.replace` to raise `KeyboardInterrupt` and assert it propagates immediately (not caught/logged as a save failure).

## 3. Correction-learning log level (`src/whispy/core/engine.py`)

- [x] 3.1 In `_detect_corrections`, change `logger.info("[corrections] learned: %s → %s", wrong, right)` to `logger.debug(...)`.
- [x] 3.2 Unit test: with the logger's effective level at `INFO` (the daemon default), trigger a detected correction and assert no `"[corrections] learned"` record is emitted (via `caplog.set_level(logging.INFO)` / no matching record).
- [x] 3.3 Unit test: with the logger's effective level at `DEBUG`, trigger a detected correction and assert the `"[corrections] learned: %s → %s"` record is emitted with the correct wrong/right values.

## 4. Fail-closed API auth (`src/whispy/api/server.py`)

- [x] 4.1 In `_authorized`, invert the token branch: when `expected` (`getattr(self.server, "auth_token", None)`) is falsy, immediately respond `401 {"error": "unauthorized"}` and return `False`; when truthy, perform the existing header/`hmac.compare_digest` check unconditionally (no `if expected:` gate around it).
- [x] 4.2 Unit test: start (or construct) a `RequestHandler`/server with `auth_token=None` and assert every exercised endpoint (`/status`, `/start`, `/stop`, `/config`) responds `401` even with correct `Host` and no `Origin`/`Referer`.
- [x] 4.3 Unit test: same as 4.2 but with `auth_token=""` (empty string) to cover the falsy-but-not-`None` case.
- [x] 4.4 Regression check: confirm existing tests in `tests/test_api/test_server.py` that set `server.auth_token = TEST_TOKEN` still pass unmodified (valid-token path unaffected).

## 5. Cross-cutting verification

- [x] 5.1 Run `./.venv/bin/pytest tests/test_config_validation.py tests/test_corrections.py tests/test_api/test_server.py tests/test_engine.py` and confirm all pass.
- [x] 5.2 Manually verify on a real (or throwaway `WHISPY_CONFIG`) install: after a config change and a learned correction, `stat -f "%OLp" ~/.config/whispy` reports `700`, and `stat -f "%OLp" ~/.config/whispy/config.json ~/.config/whispy/corrections.json` both report `600`.
- [x] 5.3 Update `CLAUDE.md`/developer docs only if the permission behavior is referenced elsewhere (grep for `0644`, `config.json`, `corrections.json` outside `src/`/`tests/`); no `website/index.html` change expected since this is not a user-facing feature/setting change.

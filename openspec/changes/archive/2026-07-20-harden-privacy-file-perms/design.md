## Context

A security audit of the local-privacy surface (the area covered by
`~/.config/whispy/`, `~/.whispy.log`, and the loopback control API) found
that two on-disk stores holding fragments of the user's dictated text are
created world-readable, a log line duplicates that data into a second
world-readable file, and one auth branch fails open rather than closed. The
codebase already has an established, tested pattern for "this file holds a
secret/private data, keep it 0600" — `auth.py` (token file) and `audio.py`
(recording WAV) — so this change is about applying that existing pattern
consistently, not inventing a new one.

## Goals / Non-Goals

**Goals**
- `config.json`, `corrections.json`, and their parent directory end up with
  owner-only permissions (`0600` / `0700`) after every save, for both fresh
  installs and upgrades from an existing world-readable install.
- The correction-learning log line no longer exposes dictated-text fragments
  at default log verbosity.
- The API auth gate cannot be bypassed by omitting/emptying the token; it
  fails closed.
- `CorrectionStore._save`'s error path no longer masks the original exception
  or catches control-flow exceptions it shouldn't.

**Non-Goals**
- No change to the data *format* of `config.json` or `corrections.json` (no
  version bump, no new migration framework).
- No encryption at rest — `0600` (owner-only) matches the threat model
  (other local users / processes), not a hostile actor with root or physical
  disk access.
- No change to the token file or recording WAV — both are already correct.
- No change to what data gets *collected* (custom vocabulary, corrections) —
  only how it's protected once written.

## Decisions

### 1. `chmod` after write, not `os.open` with an explicit mode

`audio.py:68` uses `os.open(path, O_WRONLY | O_CREAT | O_TRUNC, 0o600)` to
close the window between file creation and permission-setting, because a
recording WAV is written directly by `wave.open`. `config.py` and
`corrections.py` both already write through a temp file and `os.replace`
(atomic swap), and the temp file is created via `open()` (config.py) or
`tempfile.mkstemp()` (corrections.py). Two options:

- **(a) `os.chmod`/`Path.chmod(0o600)` on the temp file before `os.replace`,
  and again defensively on the final path after replace.**
- (b) Switch the temp-file creation to `os.open(..., 0o600)` directly (config.py) — corrections.py's `tempfile.mkstemp` already creates with `0600` by default on POSIX, so it needs no change there.

Chosen: **(a) for config.py's temp file (since `open()` doesn't take a mode
arg), verify-only for corrections.py.** `tempfile.mkstemp` already defaults
to `0600` (it's documented Python stdlib behavior, confirmed by the existing
token-file pattern's intent), so `corrections.py`'s gap is not file
creation — it's that nothing ever chmods `_path` (the final path) if an
older `0644` file already exists from a prior version, and `os.replace`
preserves the *destination* inode's permissions when replacing an existing
file only on some platforms/semantics are inconsistent enough not to rely
on. So the concrete fix is: chmod the temp file to `0600` right after
creating it (belt-and-suspenders, cheap) in both modules, and — because
`os.replace` on POSIX keeps the *replacing* file's permissions (the temp
file's), not the destination's — that alone is sufficient to make the final
`config.json`/`corrections.json` `0600` on every save, including the very
first save that replaces a pre-existing `0644` file from an old install.
This means no separate migration/startup pass is needed (see Decision 2).

Also chmod the parent directory (`config_dir`) to `0700` right after
`mkdir(parents=True, exist_ok=True)` in both `save_config` and
`CorrectionStore._save`, mirroring `auth.py`'s "set it every time, cheap and
idempotent" style rather than gating on "only if freshly created."

### 2. Migration: fix-on-next-save, not a dedicated startup pass

Two options considered:
- (a) A one-time startup routine that walks `~/.config/whispy/` and chmods
  every file/dir it finds, run once at daemon boot.
- **(b) Rely on the fact that both files are rewritten via `os.replace` on
  essentially every meaningful mutation (`save_config` is called on every
  config update via the API/menu; `CorrectionStore._save` is called on every
  learned correction and every occurrence-count bump), so the temp-file
  `0600` + `os.replace` semantics from Decision 1 self-heal an old `0644`
  file the next time either store is written — no separate migration code
  path to test or maintain.**

Chosen: **(b)**. A dedicated startup migration pass would need its own tests,
its own error handling for a read-only/missing directory, and would run on
every boot for zero benefit after the first post-upgrade save. The
self-healing property of "next write fixes permissions" is a natural
consequence of the atomic-replace pattern already in use, and is exercised
by the existing save/load test suites without new machinery. The one gap
this leaves — a file that is *read* many times but never written again after
upgrade — is negligible here because both files get written essentially
every session (config on any settings change, corrections on any learned
word), and the directory itself is chmod'd on every save call regardless of
whether a mutation occurred.

### 3. Log redaction: DEBUG level, not content redaction

Two options:
- (a) Keep `INFO` level but redact the actual words (log a hash, length, or
  `"[REDACTED]"` placeholder).
- **(b) Drop the line to `DEBUG`.**

Chosen: **(b)**. This is consistent with the rest of the audit's intent:
`~/.whispy.log` is not the place for dictated-text content at the log level
users see by default, but the *information* (that a correction was learned,
and what it was) is genuinely useful when debugging the correction feature —
redacting the content would make `DEBUG`-level troubleshooting useless.
Whispy's default log level is `INFO` (`whispy_daemon.py:40`), so `DEBUG`
lines are simply not written unless a developer explicitly raises verbosity,
which is an accepted, opt-in trade-off distinct from "world-readable by
default." No change to log file permissions is bundled here — rotating the
existing `RotatingFileHandler` to a stricter mode is out of scope for this
change since the log's `INFO`-level content is not privacy-sensitive once
this line moves to `DEBUG` (recording start/stop, status, etc. are not
dictated content).

### 4. Fail-closed auth: reject, don't fall through

`_authorized` currently reads:
```python
expected = getattr(self.server, "auth_token", None)
if expected:
    ...check header...
return True
```
So `expected` falsy (`None` or `""`) skips the check entirely and returns
`True`. Checked whether any legitimate caller starts the server tokenless:
`whispy_daemon.py:86` (headless/validation path) and `:134` (normal daemon
path) both call `load_or_create_token(CONFIG_PATH)` unconditionally before
`start_http_server`, and `load_or_create_token` always returns a
non-empty `secrets.token_urlsafe(32)` string even if persisting it to disk
fails (it only logs a warning and still returns the in-memory token). Test
suite (`tests/test_api/test_server.py`) always sets `server.auth_token =
TEST_TOKEN` before exercising the handler — no test exercises the
`auth_token is None` branch as "expected open" behavior. `start_http_server`'s
own default parameter (`auth_token: str | None = None`) is the only place a
tokenless server is reachable, and it's an internal library default, not a
supported daemon entry point. Conclusion: no production or test path relies
on the fall-open behavior, so fail-closed is safe. Change to:
```python
expected = getattr(self.server, "auth_token", None)
if not expected:
    self._json_response(401, {"error": "unauthorized"})
    return False
...check header (unconditionally)...
```

### 5. `_save` exception handling: `except Exception`, plain `try/finally`

Current code closes the fd on the success path, then in the `except
BaseException` branch does `os.close(fd) if not os.get_inheritable(fd) else
None` — calling `os.get_inheritable` on an fd that's *already closed* raises
`OSError`, which propagates instead of the original exception, and also
skips the `os.unlink(tmp)` cleanup that follows. Fix: restructure as
`try: os.write(fd, ...) finally: os.close(fd)` for the fd lifecycle, then a
separate `try: os.replace(...) except Exception: os.unlink(tmp); raise` for
the replace step, so the fd is closed exactly once regardless of outcome and
`os.unlink` cleanup always runs when `os.replace` fails, without ever
touching an already-closed fd. Narrowing to `except Exception` (from
`BaseException`) lets `KeyboardInterrupt`/`SystemExit` propagate immediately
instead of being caught by cleanup logic meant for I/O failures.

## Risks / Trade-offs

- **[Risk]** Fail-closed auth could break some caller that starts the server
  without a token, expecting open access (e.g., a future test harness or
  local debug script). **[Mitigation]** Verified via `grep` that every
  current call site (`whispy_daemon.py` normal + headless, and the entire
  `tests/test_api/test_server.py` suite) always supplies a token; add a unit
  test asserting `401` on every endpoint when `auth_token` is `None`/`""` so
  a future regression is caught immediately rather than silently reopening
  the hole.
- **[Risk]** Chmod calls on `config_dir`/file paths could raise `OSError` on
  unusual filesystems (e.g., some network home directories, exotic ACL
  setups) where `0600`/`0700` isn't representable, turning a previously
  successful save into a failure. **[Mitigation]** Wrap the chmod calls in
  the same `try/except OSError` envelope that already wraps the save logic
  in both `save_config` and `CorrectionStore._save`, so a chmod failure logs
  a warning (consistent with `auth.py`'s own `except OSError` handling
  pattern) but does not prevent the write itself from succeeding — losing
  the perms hardening on an exotic filesystem is strictly better than losing
  the save.
- **[Risk]** Moving the correction-learning log line to `DEBUG` reduces
  visibility for support/debugging when a user reports "corrections aren't
  being learned" and only has default-level logs. **[Mitigation]** The event
  itself (a correction was detected) is still inferable from
  `corrections.json` growing and from the "Learned Words" menu bar submenu;
  `DEBUG` remains available via existing log-level configuration for deeper
  troubleshooting.
- **[Trade-off]** Self-healing migration (Decision 2) means a file that is
  never rewritten after upgrade stays at its old permissions indefinitely.
  Accepted because both files are write-heavy in normal use and the
  alternative (a dedicated migration pass) adds permanent startup cost and
  test surface for a corner case.

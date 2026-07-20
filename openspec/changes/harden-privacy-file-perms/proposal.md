## Why

Whispy markets itself as "private, local" dictation, but a completed security
audit found that dictation-derived data is written world-readable and one
auth path fails open:

1. `save_config` (`src/whispy/core/config.py:342`) and `CorrectionStore._save`
   (`src/whispy/core/corrections.py:42-53`) write `config.json` and
   `corrections.json` without setting permissions, so both land at the
   process umask (verified `0644` on disk). `config.json` holds
   `custom_vocabulary` (names/jargon the user dictates); `corrections.json`
   holds learned wrong→right word pairs — fragments of the user's actual
   dictated text. The token file (`auth.py:53-54`) and recording WAV
   (`audio.py:68`) are already `0600`; the config directory and these two
   files are the odd ones out.
2. `Engine._detect_corrections` (`src/whispy/core/engine.py:541`) logs every
   learned correction pair at `INFO` (`"[corrections] learned: %s → %s"`)
   into `~/.whispy.log`, which any local user can read (`RotatingFileHandler`,
   `whispy_daemon.py:43`, default file permissions). This duplicates
   dictated-text fragments into a second world-readable location.
3. `RequestHandler._authorized` (`src/whispy/api/server.py:56`) gates the
   token check with `if expected:` — if the server is ever started with
   `auth_token=None` or `""`, every endpoint falls open to the Host/Origin
   checks alone. Not currently reachable in production (`whispy_daemon.py:86`
   and `:134` always pass a token from `load_or_create_token`, which always
   returns a non-empty string), but the check fails open rather than closed,
   so any future caller of `start_http_server` that omits a token silently
   loses the auth gate instead of erroring.
4. Bonus robustness in the same code path: `CorrectionStore._save`'s error
   handler (`corrections.py:54-55`) uses `except BaseException`, which also
   catches `KeyboardInterrupt`/`SystemExit`, and its cleanup calls
   `os.get_inheritable(fd)` on an `fd` that was already closed on the success
   path just above — an `OSError` from that call masks the original exception
   and can leak the `.tmp` file.

## What Changes

- Set `0600` permissions on `config.json` and `corrections.json` on every
  save, mirroring the existing `auth.py`/`audio.py` pattern, and `0700` on
  `~/.config/whispy` itself. Apply this both to newly created files and to
  pre-existing files from earlier installs (one-time tightening on save/load,
  no separate migration step or version bump needed).
- Drop the correction-learning log line from `INFO` to `DEBUG` so plaintext
  correction pairs no longer land in the default-visible log at normal
  verbosity.
- Change `RequestHandler._authorized` to fail closed: when no token is
  configured (`None` or empty string), reject every request with `401`
  instead of falling through to the Host/Origin-only checks.
- Fix `CorrectionStore._save`'s exception handling to use a plain
  `try/finally` with `except Exception` (not `BaseException`) so
  `KeyboardInterrupt`/`SystemExit` propagate immediately and a failed
  `os.replace` no longer masks the original error via a stale-fd call.

## Capabilities

### New Capabilities

None — file-permission behavior is folded into the existing capabilities
that own each file (`correction-store` for `corrections.json`, `core-engine`
for `config.json`, `api-interface` for the auth gate).

### Modified Capabilities

- **correction-store**: persistence requirement gains `0600` file
  permissions and the exception-safety fix in `_save`.
- **core-engine**: configuration persistence requirement gains `0600` file
  permissions (and `0700` on the config directory); the correction-learning
  log line moves from `INFO` to `DEBUG`.
- **api-interface**: the authenticated loopback control API requirement is
  tightened so a missing/empty configured token fails closed (`401` on every
  endpoint) instead of falling open to Host/Origin checks alone.

## Impact

- Affected code: `src/whispy/core/config.py`, `src/whispy/core/corrections.py`,
  `src/whispy/core/engine.py`, `src/whispy/api/server.py`.
- Affected specs: `correction-store`, `core-engine`, `api-interface`.
- Existing installs: on first save after upgrade, `config.json` and
  `corrections.json` are rewritten with `0600` and the config directory is
  tightened to `0700`; no data format changes, no user-visible behavior
  change beyond stricter file permissions and a quieter log.
- Tests: new/updated unit coverage for permissions after save (config,
  corrections), fail-closed `401` when no token is configured, and the
  `_save` exception path no longer masking the original error.

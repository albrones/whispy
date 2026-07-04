## 1. Permission and model-load visibility (`d1a2c3a`)

- [x] 1.1 `ensure_microphone_access`/`ensure_input_monitoring_access`/`ensure_accessibility_access`/`ensure_automation_access` return `True`/`False`/`None` (granted/denied/undetermined) instead of always `None`
- [x] 1.2 `Engine` gains `on_permission_missing(kind, message)` and `_notify_permission_missing`, fired only for explicit (`False`) denials
- [x] 1.3 `Engine.start()` probes all four permissions and dispatches denials with per-kind remediation text
- [x] 1.4 Menu bar registers `on_permission_missing` and the previously-orphaned `on_model_load_failed`
- [x] 1.5 Menu bar alert queue (`_pending_alerts`) generalized to carry `(subtitle, message, settings_url)`, drained on the main thread in `_tick_anim`
- [x] 1.6 Warning menu item opens the System Settings pane matching the most recent alert (`_SETTINGS_URLS` per kind)

## 2. WAV privacy (`8fe8e78`)

- [x] 2.1 `_open_recording_wav` creates recording WAVs with `0o600` via `os.open` before `wave.open`, regardless of process umask
- [x] 2.2 `_cleanup_stale_recordings` sweeps leftover `whispy-*.wav` files once at `AudioEngine` startup, best-effort (never fails startup)
- [x] 2.3 `run_transcription` deletes the recorded WAV in a `finally` block covering every exit path (no model loaded, empty/None result, raised exception)

## 3. Clipboard snapshot/restore (`8fe8e78`)

- [x] 3.1 `TextInjector._snapshot_clipboard` captures the current clipboard via `pbpaste` before it is overwritten
- [x] 3.2 `_spawn` step tuples gain an optional per-step delay; clipboard injection appends a restore (`pbcopy` with the snapshot) after the paste, delayed to let the target app read the pasted text first
- [x] 3.3 A failed paste step (e.g. `1002` denial) stops the sequence before the restore runs, leaving the transcript on the clipboard as the manual-paste fallback
- [x] 3.4 A failed snapshot (`pbpaste` missing/erroring) falls back to an empty restore rather than breaking injection

## 4. UX/operational cleanup (`8fe8e78`)

- [x] 4.1 `_on_fn_released` posts a "Model still loading" alert when the trigger is released while `state.model is None and state.model_loading`
- [x] 4.2 Event-tap failure message names Whispy and the in-app Restart action, not `python3` or a nonexistent LaunchAgent
- [x] 4.3 `~/.whispy.log` uses `RotatingFileHandler` (1 MB × 3 backups) instead of an unbounded `FileHandler`
- [x] 4.4 `install.sh --uninstall` offers (TTY-gated, defaults to "keep") removal of the config directory (incl. API token), logs, and the faster-whisper model cache
- [x] 4.5 Model-cache removal is scoped to the `models--Systran--faster-whisper-*` glob inside the shared HuggingFace hub cache, never the whole hub directory
- [x] 4.6 `scripts/bootstrap.sh` delegates `--uninstall` to `install.sh` rather than duplicating the data-removal prompt

## 5. Default language (`8fe8e78`)

- [x] 5.1 `DEFAULT_CONFIG["language"]` changes from `"fr"` to `"en"`
- [x] 5.2 All in-code fallback reads (`config.get("language", "fr")`) updated to `"en"` to match the new default
- [x] 5.3 Existing persisted configs are unaffected (`load_config` only substitutes the default for an absent key/file)
- [x] 5.4 `website/index.html` and `website/script.js` demo default to English, with French switchable from the menu

## 6. Tests + validation

- [x] 6.1 `tests/test_permissions.py`, `tests/test_engine.py` — tri-state probes and `on_permission_missing` dispatch (denials fire, granted/undetermined stay silent)
- [x] 6.2 `tests/test_menu_bar.py` — alert-callback registration, queue contents, `_show_alert` behavior with/without a settings URL, model-loading alert on `_on_fn_released`
- [x] 6.3 `tests/test_audio.py` — recording/chunk WAV permissions are `0o600` under a permissive umask; stale-sweep removes leftovers and tolerates a `glob` failure
- [x] 6.4 `tests/test_engine.py::TestRunTranscriptionCleanup` — WAV deleted whether transcription returns `None`, empty, raises, or the model isn't loaded
- [x] 6.5 `tests/test_injection.py` — clipboard snapshot/restore sequence, restore content, and safe fallback on a failed snapshot
- [x] 6.6 `tests/test_install_scripts.py` — uninstall offers data removal, scopes the model-cache glob, defaults to keep, TTY-gates the prompt, and bootstrap delegates rather than duplicating it
- [x] 6.7 `tests/test_config_validation.py`, `tests/test_e2e.py`, `tests/test_api/test_server.py` — default-language assertions updated to `"en"`
- [x] 6.8 Full suite green: 568 passed
- [x] 6.9 `openspec validate harden-v1-release --strict`

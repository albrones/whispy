## Why

A pre-v1 security/UX review of `feat/rebrand` found that the two most common
first-run failures were silent, and that a handful of privacy/UX gaps would
ship to the international v1 audience:

- **Silent failures look like a dead app**: a denied TCC permission
  (Microphone, Input Monitoring, Accessibility, Automation) and a failed
  model download both only wrote to `~/.whispy.log` — the menu bar gave no
  indication anything was wrong. The `on_model_load_failed` engine hook
  already existed but had zero UI consumers.
- **Recorded voice audio outlived its purpose**: a silent or failed
  transcription (model not loaded, empty result, or an exception) left the
  recorded WAV in the temp dir forever instead of deleting it, and the WAV
  was created under the process umask (world-readable, e.g. `0644`, in a
  shared `/tmp` on Linux) rather than owner-only.
- **Clipboard injection clobbered the user's clipboard**: pasting the
  transcript overwrote whatever the user had copied before dictating, with
  no restore.
- **Stale operational debt**: the event-tap failure message told the user to
  grant Input Monitoring to `python3` and restart via a LaunchAgent that no
  longer exists post-rebrand (the app is a signed `.app` bundle now);
  `~/.whispy.log` grew unbounded; uninstall left the config (including the
  API token), logs, and the 0.5–3 GB faster-whisper model cache behind with
  no offer to clean them up.
- **Default language excluded the v1 audience**: the shipped default was
  French (`fr`), inherited from the tool's origin, which is the wrong
  default for an internationally-marketed v1.

None of this blocks install or basic operation — the app records and
transcribes fine on the happy path — but each gap either erodes trust
(silent failures, a clobbered clipboard, leaked audio) or actively
misleads a v1 user (wrong remediation instructions, wrong default
language).

## What Changes

- **Permission and model-load visibility**: TCC probes
  (`ensure_microphone_access`, `ensure_input_monitoring_access`,
  `ensure_accessibility_access`, `ensure_automation_access`) now return
  `True` (granted) / `False` (explicit denial) / `None` (undetermined —
  system prompt pending or probe unavailable) instead of `None` always. The
  engine fans out explicit denials only (an undetermined state is noise —
  the system prompt is already handling it) through a new
  `on_permission_missing(kind, message)` callback. The menu bar registers
  both `on_permission_missing` and the previously-orphaned
  `on_model_load_failed`, posts a notification, and reveals a warning menu
  item that opens the matching System Settings pane.
- **Model-still-loading feedback**: releasing the trigger key while the
  model is still loading now raises a "still loading" notification instead
  of silently transcribing nothing.
- **WAV privacy**: recording WAVs are created with `0o600` permissions
  (owner-only, regardless of umask); `run_transcription` deletes the
  recorded WAV in a `finally` block covering every exit path (no model
  loaded, empty result, or a raised exception); `AudioEngine` startup sweeps
  stale `whispy-*.wav` files left by a prior crash.
- **Clipboard restore**: clipboard-mode injection snapshots the clipboard
  (`pbpaste`) before overwriting it, and restores the snapshot after the
  paste keystroke succeeds. If the paste itself fails (e.g. keystroke
  permission denied), the transcript is deliberately left on the clipboard
  as the documented manual-paste fallback.
- **Operational cleanup**: the event-tap failure message now names Whispy
  and points at the menu's Restart action instead of `python3` and a
  nonexistent LaunchAgent; `~/.whispy.log` rotates at 1 MB × 3 backups
  instead of growing unbounded; `install.sh --uninstall` offers (TTY-gated,
  default "keep") to remove the config directory, logs, and the
  faster-whisper model cache — scoped to the `models--Systran--faster-whisper-*`
  glob inside the shared HuggingFace hub cache, never the whole hub
  directory.
- **Default language**: `DEFAULT_CONFIG["language"]` switches from `fr` to
  `en`. Existing installs are unaffected — `load_config` only applies the
  default when a config file is absent or the key is missing, so a
  persisted `"language": "fr"` is untouched. Website copy and the animated
  demo now default to English (French remains available from the menu).

## Capabilities

### Modified Capabilities
- `text-injection`: clipboard-paste injection SHALL snapshot and restore
  the clipboard around the paste.
- `audio-capture`: recording WAVs SHALL be created owner-only (`0o600`) and
  stale `whispy-*.wav` files SHALL be swept at `AudioEngine` startup.
- `core-engine`: the default language SHALL be English; the recorded WAV
  SHALL always be cleaned up after a transcription attempt; explicitly
  denied startup permissions SHALL be surfaced through
  `on_permission_missing`; dictating while the model is still loading SHALL
  raise a notification; the model-load-failure callback SHALL actually
  reach a UI consumer.
- `event-listener`: the event-tap failure message SHALL name Whispy and the
  in-app Restart action, not `python3` or a LaunchAgent.
- `macos-install`: uninstall SHALL offer scoped, opt-in removal of user
  data (config, logs, model cache).
- `promotional-website`: the site's default-language copy and demo SHALL
  match the app's English default.

## Impact

- `src/whispy/core/engine.py` — `on_permission_missing` callback list and
  dispatch; `run_transcription` `finally` cleanup; model-loading alert path
  (via `state.model_loading`); default-language read paths.
- `src/whispy/core/config.py` — `DEFAULT_CONFIG["language"]` `fr` → `en`.
- `src/whispy/core/audio.py` — `_open_recording_wav` (0o600),
  `_cleanup_stale_recordings` (startup sweep).
- `src/whispy/platform/macos/permissions.py` — tri-state
  (`True`/`False`/`None`) return values for all four probes.
- `src/whispy/hardware/injection.py` — clipboard snapshot/restore
  (`_snapshot_clipboard`, extended `_spawn` step tuple with an optional
  delay).
- `src/whispy/hardware/event_tap.py` — corrected failure guidance text.
- `src/whispy/ui/menu_bar.py` — `_pending_alerts` queue,
  `_on_permission_missing`, `_on_model_load_failed`,
  `_on_fn_released` model-loading check, generalized `_show_alert`.
- `whispy_daemon.py` — `RotatingFileHandler` (1 MB × 3) for `~/.whispy.log`.
- `install.sh`, `scripts/bootstrap.sh` — uninstall user-data removal
  prompt.
- `website/index.html`, `website/script.js` — English-default copy and demo
  order.
- Tests: `tests/test_engine.py`, `tests/test_menu_bar.py`,
  `tests/test_permissions.py`, `tests/test_audio.py`,
  `tests/test_injection.py`, `tests/test_install_scripts.py`,
  `tests/test_config_validation.py`, `tests/test_e2e.py`,
  `tests/test_api/test_server.py` — full suite green (568 passed).

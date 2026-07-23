# Changelog V1 — Whispy

## [Unreleased]

### Added
- **Trigger key selection from the menu (macOS).** The **Settings → Trigger**
  menu lets you pick the push-to-talk key from presets (Fn, Right Command,
  Right Option, F13); the change applies live, with no restart.
- Module `src/whispy/core/config.py`: config validation and migration.
- Module `src/whispy/core/text_cleaner.py`: stripping of Whisper credits.
- Error-handling tests (`test_error_handling.py`): missing sox, unavailable
  microphone, engine without a model.
- Automatic config migration (versioning via `_version`).
- Validation of config values (`model_size`, `language`, `beam_size`, etc.).

### Changed
- **macOS install consolidated on `Whispy.app`.** A single command
  (`curl … | bash`) detects the OS: on macOS it builds and installs the
  signed `Whispy.app` bundle into `/Applications`; Linux/X11 keeps venv +
  `systemd --user`. `install.sh` no longer creates a LaunchAgent on macOS
  (autostart is the in-app "Start at login" toggle). Existing installs have
  their `com.whispy` LaunchAgent removed automatically (ending the
  double-daemon-on-`:9090` issue).
- Extracted `load_config`/`save_config` from `engine.py` into `config.py`.
- Unified model loading (`_load_model_async` + `_load_model_on_device` →
  `_load_model_async`).
- Clarified the active visualization (indicator by default).
- Improved logging of FSM transitions.
- Fixed hanging tests (mocked the `afplay` subprocess).

### Removed
- **Homebrew formula.** `packaging/homebrew/whispy.rb`, the tap bump in
  `release.yml`, the `HOMEBREW_TAP_TOKEN` secret, `docs/homebrew.md` and its
  test. (A *Cask* — the correct tool for a GUI app — remains a future option,
  blocked on notarization.)
- `whispy_legacy.py` (redundant with `whispy_daemon.py`).

### Fixed
- **Ghost checkmark in the menu.** An unchecked row kept its green checkmark
  (AppKit's `attributedTitle` takes priority over `.title`); also affected
  Model/Language and the clipboard toggle.
- **Bug: freeze at recording start.** `_wait_for_recording_ready` never
  unblocked the main thread when sox failed or timed out (missing
  `ready.set()`) — the daemon could freeze. `ready.set()` is now guaranteed
  via `finally`.
- **Audio visualization replaced.** The old ferrofluid visualization never
  rendered (the renderer targeted nonexistent APIs:
  `NSApplication.mainScreen`, `NSApplication.graphicsContext`, a mix of
  NSBezierPath/CGContext). Replaced with a simple, reliable **waveform**
  indicator (`ui/waveform_window.py`): a pill centered at the bottom of the
  screen with bars reacting to the mic, rendered with NSBezierPath/NSColor.
  Rewired into the menu bar lifecycle.
- Fixed 21 broken/blocking tests (event tap callback signature, FSM recovery
  behavior, ferrofluid wiring, API fixture that hung on transcription).
- Cleaned up duplicate keycodes in `event_tap.py` (`51` mapped both `m` and
  `backspace`, `f13`-`f20` were duplicated).

### Tooling & quality
- Diagnostic command `python whispy_daemon.py --doctor` (`make doctor`):
  checks sox, the model, the 3 macOS permissions, and the daemon status.
- Migrated linting to **Ruff** (lint + format); removed flake8.
- `Makefile`, `.pre-commit-config.yaml`, dev dependency `ruff`.
- CI: Python 3.10/3.11/3.12 matrix, `ruff check` + `ruff format --check`.

### Open source
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates.
- Real repository URLs (`albrones/whispy`); placeholders removed.
- `graphify-out/` removed from version control (generated artifact, ~7.6 MB)
  and ignored.
- Documentation moved under `docs/`; model storage documented.

### Documentation
- `AGENTS.md` updated with the actual project structure.
- `SPECIFICATION.md`: obsolete sections marked.
- README.md: up-to-date install instructions.

## [Cross-platform] — macOS + Linux/X11 (2026-06-17)

### Added
- **Linux (X11) support.** Whispy now runs on macOS **and** Linux/X11.
- **Ports-and-adapters layer** (`src/whispy/platform/`): `Protocol`
  interfaces for the OS-coupled seams (hotkey, injection, audio, tray) bound
  at runtime by `platform.detect()`.
- **Linux/X11 adapters**: hotkey via `pynput`, text injection via `xdotool`
  (+ `xclip`/`xsel`), tray via `pystray`. X11 session detection.
- **Configurable trigger key** (push-to-talk): default **Fn** on macOS,
  **Right Ctrl** on Linux; decoding by key match in addition to the Fn flag.
- **Cross-platform doctor**: checks the audio backend, `xdotool` (Linux),
  the model, platform permissions, and daemon status.

### Changed
- **Cross-platform audio backend.** Capture via `sounddevice` (PortAudio)
  instead of the `sox` subprocess, unified across macOS and Linux.
- **Per-OS dependencies** via PEP 508 environment markers:
  `pyobjc-framework-Quartz`/`rumps` on macOS, `pynput`/`pystray`/`Pillow` on
  Linux; `sox` removed.
- **macOS-only overlay.** On Linux in v1, state is exposed via the tray
  (no floating window).

### Documentation
- Promotional website and living docs (README, ROADMAP) updated: Whispy is
  no longer presented as macOS-only.

**Not covered (deferred):** Wayland, Windows, native Linux packaging, Linux
overlay.

## V1 Exit Criteria

- [x] All tests pass (297 passed, 0 failures, 0 hangs)
- [x] `install.sh` checks sox, permissions, LaunchAgent
- [x] Daemon starts and stops cleanly
- [x] Recording → transcription → injection works
- [x] Default config works without a config file
- [x] README.md up to date with install instructions
- [x] macOS permissions documented
- [x] CHANGELOG.md for V1
- [x] CI configured (GitHub Actions: Ruff lint + tests on Python 3.10–3.12)

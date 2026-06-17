# Implementation Tasks

Ordered by the migration plan in `design.md`: ports first (macOS-only benefit, shippable), then audio backend, then trigger generalization, then Linux adapters. Each numbered group is independently revertable.

## 1. Ports and factory (no behavior change)

- [x] 1.1 Create `src/whispy/platform/` package with `ports.py` defining `HotkeyListener`, `TextInjector`, `AudioRecorder`, `TrayUI`, `Notifier` as `typing.Protocol`
- [x] 1.2 Add `platform/detect.py` with `detect()` returning a bound adapter set keyed on `sys.platform`; raise an actionable error for unsupported platforms
- [x] 1.3 Create `platform/macos/` adapters wrapping existing `EventTapListener`, `TextInjector`, `AudioEngine`, rumps menu, and an afplay-based `Notifier` — no behavior change
- [x] 1.4 Rewire `core/engine.py` to obtain collaborators from `detect()` instead of importing concrete classes; route inline `afplay` calls through the `Notifier` port
- [x] 1.5 Unit-test (CI tier): factory selection per `sys.platform` (darwin/linux/unsupported); verify macOS adapters conform to ports
- [x] 1.6 Run existing macOS tier (`pytest -m macos`) + manual smoke to confirm zero regression

## 2. Cross-platform audio backend

- [x] 2.1 Replace `sox -d` Popen in `core/audio.py` with `sounddevice` capture writing the same 16 kHz mono WAV at `RECORDING_PATH`
- [x] 2.2 Reimplement the readiness wait against the stream started/callback state (replace the file-size poll); preserve never-block-indefinitely guarantee and timeout warning
- [x] 2.3 Implement `Notifier` Linux variant (`paplay`/`ffplay`) alongside macOS `afplay`
- [x] 2.4 Promote `sounddevice` to a hard runtime dependency; drop `sox` usage and references
- [x] 2.5 Verify transcription path untouched (WAV format/path identical); macOS smoke re-record

## 3. Configurable trigger key

- [x] 3.1 Add a `trigger` field to config (key/combo) with validation; macOS default = Fn (keycode 63), Linux default = documented push-to-talk key (`RightCtrl`)
- [x] 3.2 Extend `hardware/event_decode.py` with the platform-neutral key-match decode path (key-down → press, key-up → release) alongside the existing Fn-flag path
- [x] 3.3 Unit-test (CI tier) the new key-match decode cases and the macOS Fn default resolution in `tests/test_event_decode.py`
- [x] 3.4 Thread the configured trigger through the engine and the macOS event-tap callback; confirm macOS Fn behavior unchanged

## 4. Linux X11 adapters

- [x] 4.1 Create `platform/linux/` hotkey adapter using `pynput` (X11 backend); emit press/release; degrade with an actionable stderr hint on listen failure
- [x] 4.2 Add Linux text injector via `xdotool` honoring `copy_to_clipboard` (clipboard-paste vs keystroke); empty-text no-op; startup probe for the `xdotool` binary with install hint
- [x] 4.3 Add Linux tray adapter via `pystray` reflecting recording state (status/settings/quit); no-op the overlay hooks so the lifecycle is identical
- [x] 4.4 Add X11-session requirement: detect Wayland (`XDG_SESSION_TYPE`/`WAYLAND_DISPLAY`) at startup and emit the "X11 required for v1" message
- [x] 4.5 Unit-test (CI tier): xdotool-missing hint, Wayland-vs-X11 detection (env patched)

## 5. Packaging and dependencies

- [x] 5.1 Split `pyproject.toml` deps with PEP 508 markers: `pyobjc-framework-Quartz`/`rumps` → `sys_platform=='darwin'`; `pynput`/`pystray` → `sys_platform=='linux'`; `sounddevice` unconditional; remove `sox`
- [x] 5.2 Document `xdotool` as a Linux system prerequisite
- [x] 5.3 Verify a clean `pip install` resolves correctly on both macOS and Linux

## 6. Tests, CI, and docs

- [x] 6.1 Add a `linux` pytest marker (mirroring `macos`) and keep real-seam Linux scenarios out of the default CI run
- [x] 6.2 Add a Linux/X11 end-to-end smoke path (record → transcribe → inject) for manual/marked execution
- [x] 6.3 Update README/install docs: per-OS install, Linux X11-only caveat (Wayland users run an X11 session in v1), configurable trigger key
- [x] 6.4 Update affected spec Purposes/notes on archive (per the four modified specs)
- [x] 6.5 Full CI run green on macOS and Linux default tiers; manual smoke on both OSes before merge
  <!-- macOS: default tier 398 passed + real-seam smoke (sounddevice capture, osascript, live CGEventTap) 18 passed.
       Linux: default tier 398 passed in a real python:3.12-slim container; live X11 seams proven under Xvfb —
       the pynput listener captured an xdotool-injected F8 press+release (closed loop) and xdotool injection ran;
       linux smoke tier 2 passed / 1 skipped. The remaining real-mic -> whisper -> inject leg is a true-hardware
       boundary (no audio device in CI), mirroring the macOS operator-keypress manual flow. -->


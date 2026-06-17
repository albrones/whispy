## Context

Whispy is macOS-only. OS coupling is concentrated in four seams — hotkey listening (`hardware/event_tap.py`, CGEventTap/Quartz), text injection (`hardware/injection.py`, osascript), audio capture (`core/audio.py`, `sox -d` subprocess), and the tray/overlay UI (`ui/menu_bar.py` rumps, `ui/waveform_window.py` + `ui/indicator_window.py` AppKit). The core (`engine`, `state_machine`, `text_cleaner`, `config`) and several already-extracted pure modules (`event_decode`, `level_math`, `paths`, `unicode_anim`) carry no OS calls.

`engine.py` currently constructs `EventTapListener`, `TextInjector`, and `AudioEngine` directly via module imports. Trigger detection is hard-wired to the macOS Fn key (keycode 63, `NX_SECONDARYFNMASK`). `sounddevice` is already declared as a dependency but unused — capture goes through a `sox` subprocess instead.

This design adds Linux/X11 support by formalizing the four seams as ports and binding them to per-OS adapters at runtime. macOS keeps its exact current behavior.

## Goals / Non-Goals

**Goals:**
- Run Whispy end-to-end on Linux under an X11 session: configurable global hotkey → record → transcribe → inject into the focused app, with tray status.
- Introduce `Protocol`-based ports + a `platform.detect()` factory; move macOS code behind the ports unchanged.
- Generalize the trigger from "Fn key" to a configurable hotkey, Fn remaining the macOS default.
- Unify audio capture on `sounddevice` (cross-platform), retiring the `sox` subprocess.
- Keep all pure logic (ports' decisions, decode, level math) in the default CI test tier.

**Non-Goals:**
- **Wayland.** Global hotkey grab and synthetic input are restricted by Wayland's security model; deferred to a later spike (`ydotool`/`xdg-desktop-portal`). Linux v1 = X11 session only.
- **Windows.** Deferred.
- **Linux overlay windows.** The waveform/indicator NSWindow overlays stay macOS-only; Linux v1 surfaces state through the tray only.
- **Native Linux packaging** (`.deb`/AppImage/Flatpak). `pip install` only.

## Decisions

### D1 — Ports as `typing.Protocol`, adapters selected by a factory
Define structural interfaces in `platform/ports.py`: `HotkeyListener`, `TextInjector`, `AudioRecorder`, `TrayUI`, `Notifier`. `platform/detect.py` exposes `detect()` returning a bound adapter set based on `sys.platform`. `engine.py` calls the factory instead of importing concrete classes.

- *Why Protocol over ABC*: existing classes (`EventTapListener`, `TextInjector`, `AudioEngine`) already match the shapes; structural typing lets them satisfy the port with zero inheritance churn and keeps adapters decoupled from a base class.
- *Alternative — keep direct imports + `if sys.platform` branches*: rejected; scatters platform logic across the engine and defeats testability.

### D2 — Trigger generalizes to a configurable hotkey; pure decode gains a key-match path
`event_decode` keeps its Fn-flag path (macOS default) and adds a platform-neutral key-match decision keyed on a configured key/combo. Config gains a `trigger` field; macOS defaults to Fn (preserving today's behavior), Linux defaults to a documented push-to-talk key (e.g. `RightCtrl`).

- *Why*: Fn rarely emits a keycode on Linux — it is handled in firmware. A portable trigger concept is unavoidable.
- *Why push-to-talk default over a combo*: the current UX is press-and-hold; a single modifier key preserves it. Combos remain expressible in config.
- *Alternative — per-OS hard-coded trigger*: rejected; users have different keyboards/layouts, config is needed regardless.

### D3 — Linux adapters: `pynput` (hotkey), `xdotool` (injection), `pystray` (tray)
- `pynput` X11 backend for global key listen — mature, pip-installable, no root.
- `xdotool` (system binary) for clipboard-paste and keystroke synthesis, mirroring the macOS clipboard-vs-keystroke config switch. Clipboard set via `xdotool`/`xclip`-style path.
- `pystray` for the tray icon/menu — cross-platform, also a future Windows path.
- *Why xdotool over `ydotool`*: `ydotool` needs `uinput`/root and exists mainly for Wayland; X11 v1 avoids that friction.

### D4 — Audio on `sounddevice`, sounds behind a `Notifier` port
Replace `sox -d` Popen with `sounddevice` capture writing the same 16 kHz mono WAV at `RECORDING_PATH`; the cold-start "wait for file size" logic is replaced by `sounddevice`'s stream callback/started state. System sounds move behind `Notifier` (`afplay` on macOS, `paplay`/`ffplay` on Linux), so `engine.py`'s inline `afplay` calls route through the port.

- *Why*: `sounddevice` already a dep, removes the `sox` system requirement, and unifies capture so the same recorder serves both OSes.
- *Trade-off*: rewrites the capture lifecycle in `core/audio.py`; mitigated by keeping `RECORDING_PATH` + WAV format identical so transcription is untouched.

### D5 — Conditional dependencies via PEP 508 environment markers
`pyproject.toml` splits OS deps: `pyobjc-framework-Quartz; sys_platform=='darwin'`, `rumps; sys_platform=='darwin'`, `pynput; sys_platform=='linux'`, `pystray; sys_platform=='linux'`. `sox` dropped; `sounddevice` promoted to a hard runtime dep. `xdotool` documented as a system prerequisite on Linux.

### D6 — macOS overlay stays; Linux degrades to tray-only
`TrayUI` is the common surface. The AppKit overlay windows remain wired only on the macOS adapter. The Linux adapter implements `TrayUI` and no-ops the overlay hooks, so the engine drives recording state identically and the overlay is simply absent on Linux.

## Risks / Trade-offs

- **`core/audio.py` capture rewrite regresses macOS** → keep WAV path/format/`RECORDING_PATH` identical; gate behind the `macos` test tier + manual smoke before merge.
- **X11 global-hotkey reliability across DEs/WMs** → document tested DEs; `pynput` failures degrade gracefully with a clear stderr hint (mirrors today's Input-Monitoring message).
- **`xdotool` not installed** → `detect()`/injector probes for the binary at startup and emits an actionable install hint instead of silent failure.
- **Wayland user runs Whispy expecting it to work** → detect Wayland session (`XDG_SESSION_TYPE`/`WAYLAND_DISPLAY`) and print a clear "X11 session required for v1" message rather than failing opaquely.
- **Port refactor churns macOS code** → Protocol (structural) means no forced inheritance; move classes behind ports with minimal edits and keep existing tests green.

## Migration Plan

1. Land ports + factory with macOS adapters wrapping existing code (no behavior change; macOS tests stay green) — shippable on its own.
2. Switch audio to `sounddevice` + `Notifier` (macOS verified) — shippable.
3. Generalize trigger + config; Fn default preserves macOS UX.
4. Add Linux adapters (pynput/xdotool/pystray) + conditional deps + Wayland detection + per-OS docs.

Rollback: each step is independently revertable; the macOS adapter path is the existing code, so reverting the factory wiring restores prior behavior.

## Open Questions

- Linux default trigger key — `RightCtrl` push-to-talk vs a modifier combo? (Lean `RightCtrl`; revisit after dogfooding.)
- Tray icon animation parity on Linux — does `pystray` support the braille-title animation, or is a static icon acceptable for v1? (Acceptable to start static.)
- Should macOS migrate to `pystray` too for one tray path, or keep `rumps`? (Keep `rumps` for v1 — out of scope to rewrite working macOS UI.)

## Why

Whispy only runs on macOS: the hotkey listener (CGEventTap/Quartz), text injection (osascript), tray UI (rumps), and sounds (afplay) are all macOS-specific. This locks out the majority of developers who would use it. The core (engine, state machine, text cleaner, config, transcription) is already platform-neutral, so the cost of reaching Linux is bounded — the OS coupling lives behind four clear seams. This change makes Whispy run on **Linux/X11** by formalizing those seams as ports and adding Linux adapters. macOS behavior is unchanged.

## What Changes

- **Ports-and-adapters refactor** (macOS-only benefit too): formalize the OS-coupled seams as `Protocol` interfaces — `HotkeyListener`, `TextInjector`, `AudioRecorder`, `TrayUI` — and add a `platform.detect()` factory that selects the implementation at runtime. Existing macOS code moves behind these interfaces unchanged.
- **Generalize the trigger key**: the Fn-key (keycode 63, `NX_SECONDARYFNMASK`) convention is macOS-only — Fn rarely emits an event on Linux. Trigger becomes a **configurable hotkey** (push-to-talk key or modifier combo), with Fn remaining the macOS default. `event_decode` gains a platform-neutral key-match path alongside the existing Fn-flag path.
- **Linux/X11 hotkey adapter**: global key listen via `pynput` (X11 backend).
- **Linux text injection adapter**: clipboard paste / keystroke synthesis via `xdotool` (+ `xclip`/`wl-clipboard`-free path), mirroring the macOS clipboard-vs-keystroke config.
- **Cross-platform audio**: replace the `sox -d` subprocess with the already-present `sounddevice` (PortAudio) dependency, unifying capture across macOS and Linux. Sounds via a small notifier port (`afplay` on macOS, `paplay`/`ffplay` on Linux).
- **Linux tray adapter**: `pystray` for the status/menu surface. **The macOS overlay windows (waveform/indicator NSWindow) degrade to tray-only on Linux for v1** — no Linux overlay.
- **Packaging**: `pip install` with platform-conditional dependency groups (`[macos]` / `[linux]`). No `.deb`/AppImage/Flatpak in v1.

**Out of scope (deferred):** Wayland (global hotkey + synthetic input are restricted by its security model — needs a `ydotool`/portal spike), Windows, native Linux packaging, Linux overlay windows.

## Capabilities

### New Capabilities
- `platform-abstraction`: the port interfaces (`HotkeyListener`, `TextInjector`, `AudioRecorder`, `TrayUI`, notifier) and the runtime `platform.detect()` factory that binds them to a per-OS adapter.
- `linux-support`: the Linux/X11 adapter set (pynput hotkey, xdotool injection, pystray tray) and its setup/permission requirements.

### Modified Capabilities
- `event-listener`: trigger detection generalizes from the Fn-only flag convention to a configurable hotkey; pure decoding gains a key-match path. macOS Fn default preserved.
- `text-injection`: injection becomes a port with macOS (osascript) and Linux (xdotool) adapters; the clipboard-vs-keystroke contract is unchanged.
- `audio-capture`: capture backend moves from `sox` subprocess to `sounddevice`, cross-platform.
- `recording-visualization`: overlay is specified as macOS-only; Linux v1 surfaces state through the tray only.

## Impact

- **Code**: `hardware/event_tap.py`, `hardware/injection.py`, `core/audio.py`, `ui/menu_bar.py`, `core/engine.py` (swap direct imports for the factory). New `platform/` package with `ports.py`, `detect.py`, `macos/`, `linux/`. `hardware/event_decode.py` gains the key-match path.
- **Dependencies**: `pyobjc-framework-Quartz`, `rumps` become macOS-conditional; `pynput`, `pystray`, `xdotool` (system binary) become Linux-conditional; `sounddevice` promoted from unused dep to the audio backend; `sox` dropped.
- **Config**: new trigger-key config (key/combo) replacing the implicit Fn assumption.
- **Tests/CI**: existing `macos` marker stays; add a `linux` marker and an X11 smoke path. Pure ports/decode logic stays in the default (CI) tier.
- **Docs**: install instructions split per-OS; X11-only caveat documented for Linux (Wayland users run an X11 session in v1).

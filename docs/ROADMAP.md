# Roadmap

## v0.1.0 — first open-source release

- [x] Green test suite (ruff lint/format, pytest on Python 3.10–3.12)
- [x] `whispy doctor` onboarding diagnostic
- [x] OSS hygiene (license, contributing, code of conduct, templates)
- [ ] Tagged release + notes

## Cross-platform (shipped) — macOS + Linux/X11

Whispy runs on **macOS and Linux (X11)**. The OS-coupled subsystems sit behind a
ports-and-adapters layer (`src/whispy/platform/`), bound at runtime by
`platform.detect()`. The audio backend is `sounddevice`/PortAudio and the
trigger key is configurable (Fn on macOS, Right Ctrl on Linux by default).

| Subsystem | macOS | Linux (X11) |
|-----------|-------|-------------|
| Trigger key | Quartz `CGEventTap` (Fn) | `pynput` (Right Ctrl by default) |
| Text injection | `osascript` | `xdotool` (+ `xclip`/`xsel`) |
| Audio capture | `sounddevice` (PortAudio) | `sounddevice` (PortAudio) |
| Tray/menu | `rumps` menu bar + overlay | `pystray` tray (no overlay in v1) |
| Sounds | `afplay` | `paplay`/`ffplay` |

CI runs the default tier on Linux today; the per-OS real seams (X11 hotkey,
xdotool injection) live in the platform-real test tiers.

## Future work (not yet shipped)

- **Wayland** — deferred. Global hotkey capture and synthetic text input are
  restricted by Wayland's security model; needs a `ydotool`/portal spike.
- **Linux overlay window** — Linux v1 surfaces state through the tray only; a
  floating waveform/indicator (GTK/Cairo or Qt) is a later addition.
- **Native Linux packaging** — `.deb`/AppImage/Flatpak and a systemd **user**
  unit for autostart parity with the macOS LaunchAgent.
- **Windows** — not currently planned. Would require equivalents for every
  subsystem (Win32 hooks, `SendInput`, a tray library, and Task Scheduler).

Contributions welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md). Track progress
in the project [issues](https://github.com/albrones/whispy/issues).

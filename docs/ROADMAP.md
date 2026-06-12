# Roadmap

## v0.1.0 — first open-source release (macOS)

- [x] Green test suite (ruff lint/format, pytest on Python 3.10–3.12)
- [x] `whispy doctor` onboarding diagnostic
- [x] OSS hygiene (license, contributing, code of conduct, templates)
- [ ] Tagged release + notes

## Linux support (planned)

Whispy is macOS-only today: every hardware and UI subsystem is built on native
Apple frameworks. A Linux port is not a tweak — it means providing a platform
backend for each of the five subsystems below. The intended approach is to
introduce small abstraction seams (e.g. a `HardwareListener` and `Injector`
interface) and select the implementation at runtime by platform.

| Subsystem | macOS (today) | Linux candidate(s) | Notes |
|-----------|---------------|--------------------|-------|
| Trigger key | Quartz `CGEventTap` (`hardware/event_tap.py`) | `evdev` (Wayland-safe, needs input group) or `pynput` (X11) | Global key capture differs sharply across X11/Wayland. |
| Text injection | `osascript` (`hardware/injection.py`) | `wtype` (Wayland), `xdotool`/`xclip` (X11), `ydotool` (uinput) | Clipboard-paste vs synthetic keystrokes both need a backend. |
| Menu bar | `rumps` + `NSWindow` (`ui/menu_bar.py`) | `pystray` tray icon + GTK/Qt menu | No direct rumps equivalent. |
| Visualization | Waveform pill, NSBezierPath (`ui/waveform_window.py`) | GTK/Cairo or a Qt widget | Optional; ship a CLI/tray-only mode first. |
| Daemon | LaunchAgent (`install.sh`) | systemd **user** unit + install script | Autostart-on-login parity. |

Cross-cutting work:

- A platform-detection layer and a non-GUI / headless mode (record + transcribe
  + inject, no visualization) as the first Linux milestone.
- A second CI runner (`ubuntu-latest`) once a backend exists; the test suite
  already mocks the macOS-only modules, so unit tests run on Linux today.
- Audio capture (`sox`) and transcription (`faster-whisper`, `sounddevice`) are
  already cross-platform — no change needed there.

Contributions welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md). Track progress
in the project [issues](https://github.com/albrones/whispy/issues).

## Windows support

Not currently planned. Would require equivalents for all five subsystems
(Win32 hooks, `pyautogui`/SendInput, a tray library, and Task Scheduler).

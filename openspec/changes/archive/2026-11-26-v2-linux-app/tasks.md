## 1. Platform split

- [x] 1.1 macOS dependencies and `mac` module behind `cfg(target_os = "macos")`; `mac::app::run`
- [x] 1.2 Shared cpal microphone and model loader
- [x] 1.3 `v1` detection under Linux (`whispy_daemon.py`)

## 2. Linux layer

- [x] 2.1 `session` (X11 / Wayland / none)
- [x] 2.2 `x11_trigger`: XInput 2 raw events, Right Ctrl, decoder tests, clear failures
- [x] 2.3 `inserter`: enigo key by key, one backend per session, clipboard for the watchdog
- [x] 2.4 `tray` (ksni) with notification fallback; `notify` (notify-send)
- [x] 2.5 `linux::app`: composition root; Wayland leaves the key to the compositor binding

## 3. Proof

- [x] 3.1 Unit tests and clippy on Linux (container) and macOS
- [x] 3.2 `linux-e2e`: criteria 1 to 4 end to end (Xvfb, sway headless, PulseAudio)
- [x] 3.3 CI job `v2-linux`

## 4. Docs

- [x] 4.1 `v2/README.md` « Under Linux »

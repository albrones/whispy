## 1. Wayland session (`src/whispy/platform/linux/`)

- [x] 1.1 `detect()` picks Wayland adapters on a Wayland session: compositor-driven trigger (no pynput), `wtype` injector, headless tray
- [x] 1.2 `WtypeInjector`: keystrokes via `wtype`, clipboard mode adds `wl-copy`, serialized like `XdotoolInjector`
- [x] 1.3 Headless tray: blocks until quit, surfaces errors through `notify-send`
- [x] 1.4 Doctor and startup message describe the Wayland mode instead of refusing it

## 2. API

- [x] 2.1 `POST /transcribe` (raw `audio/wav`, size cap, 16 kHz mono PCM16 check, `{"text"}`, no file kept)

## 3. Omarchy + install

- [x] 3.1 `packaging/omarchy/omarchy-dictation-whispy` (`start|stop|toggle`, notification + non-zero exit when Whispy does not answer)
- [x] 3.2 `install.sh`: Wayland tool check, adapter link in `~/.local/bin`, unit bound to `graphical-session.target` when active

## 4. Docs and tests

- [x] 4.1 Unit tests (detection, wtype injection, headless tray, `/transcribe`, adapter script); FEATURE_MATRIX rows
- [x] 4.2 README, install/troubleshooting docs, website, AGENTS/CLAUDE, CHANGELOG; `make docs`

## 5. Delivery

- [x] 5.1 Installed in the Omarchy VM, `omarchy-dictation-use whispy`, criteria proven

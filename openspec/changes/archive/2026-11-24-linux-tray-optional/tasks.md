## 1. Config and adapters

- [x] 1.1 `tray_icon` key in `CONFIG_SCHEMA` (bool, default true, group Startup)
- [x] 1.2 `make_tray` under X11 returns the notification-only tray when `tray_icon` is false, and logs it

## 2. Fallback

- [x] 2.1 `PystrayApp.run()` catches a failing tray start, logs, notifies once and runs notification-only
- [x] 2.2 `quit()` stops the fallback too and stays safe before `run()`

## 3. Doctor, docs and tests

- [x] 3.1 `tray icon` doctor check (OK on Wayland / off in config / pystray loads, WARN otherwise)
- [x] 3.2 Unit tests (adapters, fallback, doctor)
- [x] 3.3 Troubleshooting entry, install page, website, CHANGELOG; `make docs`

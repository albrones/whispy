## Why

Under macOS, Whispy V2 (Rust) is the only version (#52). Under Linux it is
still V1 (Python). Issue albrones/whispy#51 is the first of three cards that
move Linux to V2: this one delivers the `whispy2` app itself under X11 and
under Wayland (Omarchy). The Omarchy integration (bar panel, pill, key) and
the installation (bootstrap, `systemd --user`, site, V1 removal) follow and
depend on it.

## What Changes

- `whispy2` builds on Linux. The macOS layer (`src/mac`, its composition root
  now `mac::app`) and its dependencies are macOS-only; a Linux layer
  (`src/linux`) sits next to it. `main.rs` picks the platform's `run()`.
- Shared: the controller, the machine, the control socket, the journal, the
  log, the settings, and the cpal microphone (moved out of `src/mac`), plus
  the model loader (`controller::load_models`).
- Linux layer:
  - `session`: X11, Wayland or no display, from `XDG_SESSION_TYPE`,
    `WAYLAND_DISPLAY`, `DISPLAY`.
  - `x11_trigger`: Right Ctrl (V1's Linux default) through XInput 2 raw key
    events on the root window, no grab; autorepeat ignored; another key while
    held is `OtherKeyDown`. Any failure is a sentence for the user, never a panic.
  - `inserter`: enigo, one key at a time (the input-method path of
    `Enigo::text` loses text in terminals under Wayland), with only the
    session's backend able to connect (XWayland would type twice).
    The watchdog's clipboard: `wl-copy`, `xclip`, `xsel`.
  - `tray` (ksni): grey ring at rest, red dot while listening, status line, Quit.
    X11 only. If it cannot start, one notification and Whispy runs on.
  - `notify`: alerts through `notify-send`.
  - Under Wayland nothing listens to a key: the compositor binding calls the
    control socket (`start`, `stop`, `toggle`).
- `v1`: under Linux, V1 is a process running `whispy_daemon.py` (or port 9090).
- No network port. Not ported: `custom_vocabulary`, `POST /transcribe`, `GET /level`.
- `whispy2/linux-e2e/`: a Docker kit that proves the four criteria end to end.
- CI: a `v2-linux` job (tests and clippy of `whispy2` and `whispy-core` on Ubuntu).

## Cost

| dependency | why | weight |
|---|---|---|
| `x11rb` 0.13.2 (`xinput`) | the trigger key under X11, pure Rust, no libxcb; enigo uses the same version | Linux only |
| `enigo` 0.6.1 (`x11rb`, `wayland`, no `xdo`) | typing under X11 (XTest) and Wayland (virtual keyboard), chosen at the cadrage | Linux only; links `libxkbcommon`, present on every Wayland desktop |
| `ksni` 0.3.7 (`async-io`, `blocking`, no tokio) | the X11 tray icon (StatusNotifierItem), chosen at the cadrage | Linux only; pure Rust D-Bus (`zbus`) |

Refused at the cadrage: an HTTP API on `:9090`, `rdev`/`evdev` for the key,
`xdotool`/`wtype` for typing.

## Impact

- New capability `v2-linux-app`.
- macOS: behaviour unchanged (same adapters, moved: `main.rs` → `mac/app.rs`,
  `mac/microphone.rs` → `microphone.rs`).
- Users: nothing installs the Linux app yet (card 3/3); the website is unchanged.

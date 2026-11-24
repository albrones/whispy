## Why

A Linux user could not get Whispy running and blamed graphics drivers. Under
X11 the only graphical piece is the `pystray` tray icon, and inference is
CPU-only. When the tray cannot start (no working pystray backend, no X
display, a GTK error), `PystrayApp.run()` raises, the daemon dies and
`systemd` restarts it in a loop. A decorative icon must never stop dictation.

## What Changes

- **Automatic fallback**: when the tray cannot start, Whispy logs the reason
  and the remedy, posts one desktop notification, then keeps running with the
  notification-only surface (the one Wayland already uses). `quit()` still ends
  it, so SIGTERM exits cleanly.
- **Explicit opt-out**: new `tray_icon` config key (default `true`). When
  `false`, Whispy does not start the tray under X11. This is the way out of a
  tray that crashes the process (a GTK segfault cannot be caught in Python).
- **`whispy --doctor`**: a `tray icon` check (warning, not failure, when
  pystray does not load).
- Docs, troubleshooting entry, website and changelog updated.

## Impact

- Capability: `linux-support` (modifies "Linux tray UI").
- Default behaviour is unchanged where the tray works. macOS ignores `tray_icon`.
- No new dependency.

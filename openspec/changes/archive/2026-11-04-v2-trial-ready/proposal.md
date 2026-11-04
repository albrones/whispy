## Why

Whispy V2 (`v2/`) was benched against V1 on 2026-10-17 but has never been used
day to day. It runs from a terminal, its macOS permissions go to that terminal,
it does not start at login, and it shows nothing while you speak except its
menu icon. So V1 stayed the app in use, and only V1 kept evolving. The user has
decided that V2 will replace V1. Before porting the rest of V1, V2 has to
survive a 3–5 day trial with V1 quit. That trial needs a V2 you can live with,
and exit criteria written down before it starts.

## What Changes

- **An installable, signed `Whispy V2.app`** (bundle id `com.whispy.v2`) in
  `/Applications`. It is built and signed with V1's existing self-signed
  identity, so macOS keeps its permissions across rebuilds. It is a menu bar
  app (no Dock icon) and installs next to V1's `Whispy.app` without replacing
  it. `make v2-reinstall` rebuilds it, replaces the installed copy and
  relaunches it, like V1's `make reinstall`.
- **Start at login**: a menu toggle backed by the OS login-item service. The
  OS state is the only source of truth, so there is no config file.
- **A local control socket** at `~/.whispy/v2/control.sock`, in an owner-only
  directory, with a line protocol: `start`, `stop`, `toggle`, `status`. It
  replaces V1's `:9090` API for scripts and tests. It is the trigger Linux
  Wayland will use later, and it doubles as the single-instance lock: a second
  launch finds a live socket and exits.
- **A recording indicator**: a small floating panel that never takes focus.
  It shows "recording" with a live input level, then "transcribing", on top of
  every Space, including full-screen ones. The ferrofluid pill is not ported.
- **"Microphone heard nothing"**: a dictation of 0.5 s or more whose level (30 ms
  window RMS × 10, V1's scale) stays under V1's noise floor (0.1) inserts nothing, plays a failure sound and
  says so in the menu, naming the input device. Such a dictation is not kept
  as lost speech.
- **A log file** at `~/.whispy/v2/whispy2.log`, rotated by size. It records
  state changes, errors and one line per dictation (duration, latency, engine,
  outcome, text length). It never records the dictated text.
- **Trial measurement**:
  - Each dictation appends one JSON line to `~/.whispy/v2/dictations.jsonl`.
  - `banc --trial` reports from that file: dictation count, lost and empty
    rates, and release-to-insert latency p50/p95.
  - It reads V1's lost-speech rate from `~/.whispy.log` and sets the two side
    by side.
  - `v2/TRIAL.md` states the exit criteria and the go/no-go procedure.
- **Platform seams**:
  - Every new piece is either portable (socket, log, dictation journal) or
    sits behind a port with its macOS adapter in `whispy2/src/mac/`
    (indicator, login item, heard-nothing sound).
  - `whisper-rs`'s `metal` feature becomes macOS-only, so the workspace can
    compile on Linux later.

## Capabilities

### New Capabilities
- `v2-macos-install`: the V2 bundle (build, signing, install next to V1,
  reinstall) and its login item.
- `v2-app-control`: the local control socket, its protocol and its role as
  the single-instance lock.
- `v2-trial`: the per-dictation journal, the `banc --trial` report, the
  comparison with V1, and the written exit criteria.

### Modified Capabilities
- `v2-menu-bar-app`: adds the recording indicator, the "microphone heard
  nothing" report, the default input device being reopened for each
  dictation, and the rotated log file. The terminal is no longer the app's
  log.

## Raison d'être

- **Usage:** every dictation, many times a day, for the 3–5 days of the trial,
  then for good if the trial passes.
- **Without it:** V2 stays a bench, V1 keeps drifting further ahead, and the
  switch never happens.

## Refusé

- **Porting streaming, language drift, custom vocabulary or a settings UI
  now.** Whether any of them is needed is what the trial decides. A parity
  change written after the trial picks them up.
- **Linux.** It is a separate change, `v2-linux-wayland`, after the switchover.
  Omarchy is Hyprland/Wayland, so V1's X11 support is no reference. This
  change only keeps the seams open.
- **Replacing `/Applications/Whispy.app` or reusing `com.whispy`.** During the
  trial V1 must stay one click away. The rename happens at the switchover.
- **An HTTP API like V1's `:9090`.** A Unix socket in an owner-only directory
  needs no bearer token and no open port.
- **Engine-update watch** (pinning plus a bench gate on new Parakeet
  releases). It comes after the switchover, on V2 only.

## Coût

- `objc2-service-management` (pinned exactly, like every V2 dependency) for
  `SMAppService`, plus AppKit features for the indicator panel, which come
  from crates already in use.
- No other new crate: the socket, the log rotation and the JSON lines use
  `std` only. No `serde` is in the V2 tree, and the journal's lines are flat
  enough to write by hand.
- At run time: one more thread (socket accept), one non-activating panel
  shown only while recording or transcribing.

## Impact

- Code: `v2/whispy2/` (main, controller, new `control`, `log`, `journal`
  modules, new `mac/indicator.rs`, `mac/login_item.rs`), `v2/whispy-core`
  (target-conditional `metal`), `v2/banc` (`--trial`).
- Packaging: new `packaging/macos-v2/` (Info.plist, bundle script), `Makefile`
  targets `v2-app` and `v2-reinstall`.
- Docs: `v2/README.md` (install, socket, trial) and the new `v2/TRIAL.md`.
- Builds on `banc --labelled` (#34, on `origin/main`): implementation branches
  from `origin/main`.
- V1, its bundle, `:9090` and `~/.whispy/lost/` are untouched. The website is
  untouched too: V2 is not offered to users until the switchover change.

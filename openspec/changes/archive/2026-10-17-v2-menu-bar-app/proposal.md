## Why

Whispy V2's first half (`v2-transcription-core`) turns a dictation's PCM into
text, but nothing yet records a dictation or puts its text anywhere. Card #1
(Régie, project whispy) asks for one Rust binary that does what V1 does day to
day — menu bar icon, Fn held to dictate, Fn released to insert, a short tap to
toggle — measured from Fn release to inserted text, and that never fights V1
for the Fn key.

## What Changes

- New crate `v2/whispy2` (binary `whispy2`, plus a library for its tests):
  - `machine`: an explicit, pure state machine — idle, recording (hold or
    toggle), transcribing, inserting, yielded to V1 — with a 0.3 s tap
    threshold, a 5 min recording watchdog (text left on the clipboard), and Fn
    used as a modifier cancelling its dictation.
  - `controller`: runs the machine on its own thread, the `Pipeline` and the
    inserter on a worker thread; ports `Capture` and `Inserter`.
  - `mac`: listen-only CGEventTap on Fn (keycode 63, secondary-Fn flag), cpal
    microphone opened per dictation and resampled to 16 kHz, V1's
    clipboard + System Events ⌘V insertion, NSStatusItem menu.
  - `v1`: V1 detection (port 9090 answers, or a `Whispy.app/Contents/MacOS/Whispy`
    process), checked at start and every 2 s.
- `tests/latency.rs`: end-to-end latency with a WAV for the microphone and a
  recorder for the paste, real models (ignored by default, needs them).
- Empty-or-failed dictations kept as WAV in `~/.whispy/v2-lost/`.
- `v2/README.md`: how to launch, permissions, cohabitation, latency.

## Measured (2026-10-17, M1 Pro)

- **Criterion 4:** Fn release → text delivered, 43 dictations of 6.5–6.8 s:
  p50 0.31 s, **p95 0.37 s**, max 0.41 s (target 1.5 s). The real paste adds
  ~0.1 s of process starts (`pbpaste`, `pbcopy`, `osascript`).
- **Criterion 6:** with V1 running (`/Applications/Whispy.app`, port 9090),
  `whispy2` started, read its menu through the Accessibility API: « Whispy V1
  is running — Fn is left to it », icon « paused while V1 runs ». Quit from the
  menu exits cleanly.
- **Criterion 1:** the binary builds with `cargo build --release`, shows its
  icon, installs the Fn tap. A real Fn press and a real paste need the user's
  keyboard and V1 stopped: `[à l'usage]`.

## Raison d'être

- **Usage:** every dictation, many times a day, once V1 is quit.
- **Without it:** V2 exists only as a bench; the user keeps V1 and its lost
  speech.

## Refusé

- **Streaming and live typing** (V1's chunked mode) — the card asks for
  dictate-then-insert first; the pipeline already bounds memory per 20 s.
- **An app bundle, login item, settings window, other trigger keys** — not in
  the card; the binary runs from a terminal.
- **Keeping the microphone open between dictations** (pre-roll) — the macOS
  recording indicator would stay on; opened per dictation like V1.
- **CGEventPost for the paste** — V1 measured it silently dropped for a
  self-signed app; System Events is the path that works.
- **`tray-icon`/`tao`, `rubato`** — a status item and a windowed-sinc
  resampler are a few dozen lines on crates already needed.
- **Stopping or reconfiguring V1** — V2 yields; V1 is not touched.

## Coût

- `cpal =0.16.0`: CoreAudio capture of the default input.
- `core-graphics =0.25.0`, `core-foundation =0.10.1`: the Fn event tap and the
  run loop it attaches to.
- `objc2 =0.6.5`, `objc2-foundation =0.3.2`, `objc2-app-kit =0.3.2`,
  `dispatch2 =0.3.1`: the menu bar item, and status updates hopped to the main
  queue; AppKit features trimmed to the classes used.
- `libc` (already a dependency): process list for V1 detection.
- No network call. Run time: one menu bar item, three threads, a 1 s
  housekeeping beat (watchdog, tap health, V1 check every 2 s).

## Capabilities

### New Capabilities
- `v2-menu-bar-app`: the macOS app around the V2 core — Fn hold and toggle,
  insertion, menu bar status, V1 cohabitation, end-to-end latency.

### Modified Capabilities
_None._

## Impact

- New: `v2/whispy2/`; `v2/Cargo.toml` (workspace member), `v2/Cargo.lock`,
  `v2/README.md`.
- CI: the existing `v2` job (fmt, test, clippy) now covers the crate; the
  latency test is ignored there (no models).
- V1, its install and `~/.whispy/lost/` untouched.

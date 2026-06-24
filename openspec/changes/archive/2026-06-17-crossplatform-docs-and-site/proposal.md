## Why

Whispy now runs on **macOS and Linux/X11**: the OS coupling lives behind a
ports-and-adapters layer (`platform.detect()`), the trigger key is configurable
(Fn on macOS, Right Ctrl on Linux by default), and audio capture uses
`sounddevice`/PortAudio rather than a `sox` subprocess. The README already
reflects this — but the **promotional website** and two **living docs**
(`docs/ROADMAP.md`, `CHANGELOG.md`) still describe a macOS-only,
Fn-only, sox-based product. The site greets every visitor with "voice dictation
for macOS" and an install block that lists `sox` as a requirement, and ROADMAP
files Linux under "planned." These are now wrong and undersell what shipped.

This change updates the user-facing surfaces to the cross-platform reality. No
application code changes; documentation and the static site only.

## What Changes

- **Website de-macOS-centered** (`website/`): the site stops being macOS-centric
  and presents Whispy as cross-platform (macOS + Linux/X11) throughout —
  title/meta/OG, hero, features, how-it-works, install, and footer.
  - Trigger copy generalizes from a hard-coded `Fn` to the configurable
    push-to-talk key (Fn default on macOS, Right Ctrl default on Linux).
  - Install section gains a **Linux path** (xdotool + PortAudio prerequisites)
    and **drops the wrong `sox` requirement** (audio is `sounddevice`/PortAudio).
  - The interactive demo is no longer presented as a macOS-only artifact:
    framing/copy cover both platforms (see design decision in `design.md`).
- **`docs/ROADMAP.md`**: move Linux/X11 from "planned" to **shipped**; reframe
  remaining future work (Wayland, Windows, Linux overlay window, native Linux
  packaging) as the open items. Drop the stale "macOS-only today" / "audio uses
  sox" statements.
- **`CHANGELOG.md`**: add an entry covering the cross-platform release —
  ports-and-adapters layer, Linux/X11 adapters (pynput/xdotool/pystray),
  configurable trigger, `sounddevice` audio backend, per-OS PEP 508 deps, and
  the Linux checks in `doctor`.

**Out of scope:** README (already current); historical/audit snapshots
(`docs/SPECIFICATION.md`, `docs/code-audit.md`, `docs/REVIEW_V1_PLAN.md`) — their
`sox` references are dated point-in-time records and are left as-is; any
application code; Wayland/Windows site copy beyond noting them as unsupported.

## Capabilities

### Modified Capabilities
- `promotional-website`: the value-proposition and install content generalize
  from macOS-only to cross-platform (macOS + Linux/X11); the trigger is
  described as configurable rather than Fn-only; the install requirement no
  longer names `sox`.

## Impact

- **Docs/site**: `website/index.html`, `website/styles.css`, `website/script.js`
  (only as needed for demo framing), `docs/ROADMAP.md`, `CHANGELOG.md`.
- **Tests**: `tests/test_website.py` asserts presence of anchors
  (`features`/`how`/`privacy`/`install`), brand green `#24bf9e`, the repo URL,
  `Whispy`, a meta description, and `prefers-reduced-motion` — all preserved by
  this change. No test changes expected; re-run to confirm.
- **No code, no dependency, no config changes.**

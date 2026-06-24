# Implementation Tasks

Docs/site only — no application code. Each group is independently revertable.

## 1. Website — cross-platform copy (`website/index.html`)

- [x] 1.1 `<title>`, `<meta name="description">`, and all OG/Twitter tags: replace "for macOS" / "leaves your Mac" with cross-platform framing (macOS + Linux/X11)
- [x] 1.2 Hero: tagline + lede cover both platforms; "Apple Silicon and Intel" note generalizes (add Linux/X11)
- [x] 1.3 Trigger copy: replace hard-coded `Fn` references with the configurable push-to-talk key; note "Fn on macOS, Right Ctrl on Linux by default" once near the hero/demo
- [x] 1.4 Features + how-it-works: degeneralize macOS-only language; keep `kbd` affordance generic
- [x] 1.5 Privacy section: "Runs on your Mac" → "Runs on your machine" (macOS or Linux)

## 2. Website — install section (`website/index.html`)

- [x] 2.1 Drop the wrong `sox` requirement; state audio uses `sounddevice`/PortAudio
- [x] 2.2 Add a Linux/X11 install path: distro deps (`xdotool`, optional `xclip`/`xsel`, PortAudio runtime) + the bootstrap one-liner; keep the X11-only caveat
- [x] 2.3 Keep the `#install` anchor and copy-button targets intact

## 3. Website — demo framing (`website/script.js`, `website/styles.css`)

Per `design.md` Option B (platform-neutral chrome):
- [x] 3.1 Neutralize macOS-specific chrome in the demo mock (Apple glyph, traffic-light controls) to a generic window/menu surface
- [x] 3.2 Key cap label generalizes from `Fn` to the push-to-talk concept
- [x] 3.3 Preserve the `prefers-reduced-motion` guards in both CSS and JS

## 4. `docs/ROADMAP.md`

- [x] 4.1 Retitle/restructure so Linux/X11 is **shipped**, not "planned"
- [x] 4.2 Remove "Whispy is macOS-only today" and the "audio uses sox" line
- [x] 4.3 Reframe open future work: Wayland, Windows, Linux overlay window, native Linux packaging

## 5. `CHANGELOG.md`

- [x] 5.1 Add a cross-platform release entry: ports-and-adapters layer + `platform.detect()`, Linux/X11 adapters (pynput/xdotool/pystray), configurable trigger, `sounddevice` audio backend, per-OS PEP 508 deps, `doctor` Linux checks

## 6. Verify

- [x] 6.1 Run `./.venv/bin/pytest tests/test_website.py -v` — all green (anchors, brand green, repo URL, meta description, reduced-motion preserved)
- [x] 6.2 Open `website/index.html` in a browser; confirm cross-platform copy, Linux install path, and demo render correctly
- [x] 6.3 Skim README ↔ site for consistency (trigger defaults, prerequisites, install commands)

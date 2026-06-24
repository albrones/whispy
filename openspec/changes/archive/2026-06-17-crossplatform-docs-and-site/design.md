# Design Notes

## Decision: how to de-macOS-center the interactive demo

The demo (`website/script.js` + `.demo-*` styles) is the visual centerpiece: a
fake **macOS** menu bar (Apple logo, traffic-light window controls, `Fn` key
cap) animating record → transcribe → type. The user's directive is that the site
is "no longer macOS-centric." Three options:

| Option | Effort | Result |
|--------|--------|--------|
| **A. Copy-only** | low | Keep macOS chrome; reword surrounding copy to cover both OSes. Cheapest, but the centerpiece still *looks* macOS-only — weakest fit for "not macOS-centric." |
| **B. Platform-neutral chrome** | medium | Strip OS-specific chrome (Apple logo, traffic lights) to a generic window/menu-bar; key cap reads "push-to-talk" not `Fn`. Honest cross-platform without per-OS forks. |
| **C. Platform toggle** | high | A macOS/Linux switch that re-skins the demo (menu bar vs tray, Fn vs Right Ctrl). Most faithful, most JS/CSS work and most test surface. |

**Chosen: B (platform-neutral chrome), with a path to C later.** It satisfies
"not macOS-centric" by removing the macOS-specific signifiers from the
centerpiece, keeps the single animation (low risk, no per-OS branching), and the
key cap shows the push-to-talk concept rather than a specific key. A platform
toggle (C) can be a follow-up if we want to showcase the Linux tray surface
explicitly.

Concretely under B:
- Window controls: neutral dots / generic title bar instead of macOS traffic
  lights; drop the Apple glyph from the menu-bar mock.
- Key cap: label the push-to-talk affordance generically; mention "Fn on macOS,
  Right Ctrl on Linux" in copy near the demo, not on the cap.
- The tray/menu-bar metaphor stays (both platforms have a tray/menu surface);
  copy notes Linux shows state via the tray (no floating overlay in v1).

## Non-goals

- No platform-detection JS that changes the demo per visitor OS (that's C).
- No screenshots/recordings of a real Linux session in v1.
- No change to the brand palette, layout system, or reduced-motion handling.

## Test safety

`tests/test_website.py` is content-presence only: anchors
`features`/`how`/`privacy`/`install`, brand green `#24bf9e`, repo URL, `Whispy`,
a `<meta name="description">`, and `prefers-reduced-motion` in CSS and JS. Option
B keeps all of these. Keep the four anchor IDs and the reduced-motion guards
intact; re-run the suite after edits.

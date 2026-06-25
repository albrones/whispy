# Testing tier convention

Every scenario in the capability specs is tagged with exactly one **test tier**
describing the highest-fidelity level at which it is meaningfully verified.
The tag appears as an italic line directly under the scenario.

| Tier | Meaning | Runs in CI? | Trust |
|------|---------|-------------|-------|
| `unit-pure` | Pure logic, no OS/hardware/external process. | yes | high — green means correct |
| `unit-mocked` | Orchestration verified with Quartz/sox/Whisper/subprocess mocked. | yes | medium — green proves wiring, not the real seam |
| `live-driven` | Real daemon booted and driven over its HTTP API (real mic + model + injection); unattended. | no (local / `make validate`) | high for the seam — proves the running app, minus the physical keypress |
| `macos-real` | Requires a real Mac: event tap, audio device, osascript injection, real Whisper model. | no (local / `@pytest.mark.macos`) | proves the macOS user-facing seam |
| `linux-real` | Requires a live Linux/X11 session: pynput listener, real audio device, xdotool injection, real Whisper model. | no (local / `@pytest.mark.linux`) | proves the Linux/X11 user-facing seam |
| `manual-ui` | Menu bar / windows / physical trigger keypress + visual confirm; checked by a human (harness-assisted). | no (local / `make validate` operator layer) | lowest — needs a human, but recorded per run |

A `live-driven`/`macos-real`/`linux-real`/`manual-ui` tag means a passing CI run
does **not** prove that scenario: the real boundary is mocked or unexercised in
CI. Those scenarios are exercised by `make validate` (see the `release-validation`
capability), where an unexercisable seam reports **UNVERIFIED** — never a silent
pass.

Origin: change `define-test-perimeter` (see its `design.md` for the full
scenario→tier matrix and verification findings).

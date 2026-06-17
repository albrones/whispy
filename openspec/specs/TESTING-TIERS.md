# Testing tier convention

Every scenario in the capability specs is tagged with exactly one **test tier**
describing the highest-fidelity level at which it is meaningfully verified.
The tag appears as an italic line directly under the scenario.

| Tier | Meaning | Runs in CI? | Trust |
|------|---------|-------------|-------|
| `unit-pure` | Pure logic, no OS/hardware/external process. | yes | high — green means correct |
| `unit-mocked` | Orchestration verified with Quartz/sox/Whisper/subprocess mocked. | yes | medium — green proves wiring, not the real seam |
| `macos-real` | Requires a real Mac: event tap, audio device, osascript injection, real Whisper model. | no (local / `@pytest.mark.macos`) | only tier that proves the user-facing behavior |
| `manual-ui` | Menu bar / windows; checked by hand. | no | lowest — no assertion today |

A `macos-real`/`manual-ui` tag means a passing CI run does **not** prove that
scenario: the real boundary is mocked or unexercised. Those scenarios are the
work-list for the follow-up test changes (event-tap/UI coverage, semantic
transcription tests, and a real end-to-end smoke test).

Origin: change `define-test-perimeter` (see its `design.md` for the full
scenario→tier matrix and verification findings).

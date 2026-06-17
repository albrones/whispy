## Context

D→C→B left exactly three behaviors unverified, all OS-bound: `sox` mic capture, `osascript` injection, and the `CGEventTap`. The chosen shape is **unattended partial** — automate everything that can run without a human or synthetic input, and draw an explicit boundary at the parts that genuinely need an operator (a real Fn keypress, a focused text field receiving Cmd+V). Two hard constraints shape the design: `tests/conftest.py` mocks `Quartz` and `rumps` globally (so real-Quartz code can't run in-process), and CI has no mic/permissions (so every seam must skip cleanly).

## Goals / Non-Goals

**Goals:**
- Verify the three real seams on a permitted dev Mac, unattended.
- Skip — never fail — when a device or permission is absent.
- Keep these out of default CI (already handled by `addopts = -m 'not macos'`).

**Non-Goals:**
- Synthetic Fn keypress via `CGEventPost` (needs Accessibility; flaky) — out of scope.
- Cmd+V paste into a focused field — operator-verified, documented, not automated.
- Virtual audio devices (BlackHole) — not introduced; capture is asserted as "valid WAV", not "expected words" (that is step B's job).
- Any `src/` change.

## Decisions

### Decision: Live event tap runs in a subprocess
`conftest.py` does `sys.modules["Quartz"] = MagicMock()` before any import, so within pytest `CGEventTapCreate` is a mock and can never produce a real tap. The smoke test therefore spawns a fresh `python -c` subprocess (with `PYTHONPATH=src`, no conftest) that imports `whispy.hardware.event_tap`, starts an `EventTapListener`, and prints `ACTIVE`/`INACTIVE`. The test asserts `ACTIVE`, or skips on `INACTIVE` (Input Monitoring not granted → `CGEventTapCreate` returns `None` → `active` stays False). Alternative (unmock Quartz mid-test) rejected — fragile and pollutes other tests.

### Decision: osascript seam tested via clipboard round-trip, not Cmd+V
`TextInjector._inject_via_clipboard` sets the clipboard *and* fires Cmd+V in one `osascript` call. Firing Cmd+V unattended would paste into whatever window has focus (the test runner) — unsafe and unverifiable. Instead the test exercises the real `osascript` automation seam directly: set a unique token via `osascript`, read it back with `pbpaste`, assert equality. This proves the machine's `osascript` text path works (the foundation injection relies on); the paste-into-field step is the operator boundary.

### Decision: Audio capture asserts validity, not content
The test drives the real `AudioEngine.start()/stop()` against the default device for a short interval and asserts the temp WAV is readable (`wave` module), 16 kHz mono, and larger than the readiness threshold. It does not assert what was heard — silence is fine. Content fidelity is step B; this is purely "the capture seam works on real hardware".

### Decision: Every seam skips cleanly
Missing `sox`/`osascript`/`pbpaste` → module-level skip. No input device or `sox` error → skip the capture test. Subprocess reports `INACTIVE` → skip the tap test with a message pointing at Input Monitoring. Skips keep the layer honest on machines/CI that can't run a given seam.

## Risks / Trade-offs

- **Permissions vary by machine** → the value of A is partly environmental; mitigated by clear skip messages so a skip is understood as "not granted here", not "passed".
- **`sox` opening the default device may prompt for Microphone permission** on first run → documented; skips on error.
- **Subprocess model load time** is nil here (no Whisper) — the tap subprocess is fast.

## Open Questions

- Should the operator manual flow (hold Fn → speak → see text appear) be captured as a checklist doc in the repo, or left in this design? Default: a short note in the test module docstring; promote to a doc only if it grows.

## Why

The default test suite (~227 tests) is green even when the running app is dead: `conftest.py` mocks Quartz/rumps/audio, so `make test` proves wiring, not behavior. The real-seam tiers (`pytest -m macos|linux`) **skip** when a permission or device is absent — an all-skip run is indistinguishable from an all-pass run. The one flow users actually exercise (hold trigger → speak → release → text lands in the focused app) is documented as the "operator manual flow" and is run by nobody on a schedule. That is exactly where breakage lives, on both macOS and Linux/X11. We need one easy-to-trigger, easy-to-maintain system that verifies real features and whose coverage provably grows with every fix and feature.

## What Changes

- Add a single entrypoint with two faces: a `make validate` orchestrator (portable source of truth) and a `/validate` Claude Code skill that wraps it and triages the output.
- `make validate` runs three honest layers for the current OS:
  1. **Preflight** — `doctor`: permissions, model cached, mic, `xdotool` (Linux), daemon state.
  2. **Live-drive** — boot the **real** daemon and drive it over its existing HTTP API (`GET /status /config /last-transcription`; `POST /start /stop /stop-async /config`), asserting real state transitions and transcription content against real mic + model + injection. No mocks at this layer.
  3. **Operator** — guided interactive checklist for the human-only residue (physical trigger keypress + visual confirm of injected glyphs); the harness pre-arms and watches the API to auto-detect results where it can, recording PASS/FAIL per feature.
- **BREAKING (reporting contract):** skips become **loud**. A seam that cannot run reports `UNVERIFIED` as a distinct outcome, never silent PASS. The run summary states "N seams UNVERIFIED" so green never means "ran nothing."
- Add `FEATURE_MATRIX.md`: every user-facing feature → its coverage tier (`unit-pure` / `unit-mocked` / `live-driven` / `manual-ui`) → how to verify. Single source of truth, covering macOS and Linux/X11 in parity.
- Add a **maintenance discipline rule**: any bug fix or feature change MUST (a) update the matrix row and (b) add a regression case at the lowest layer that can catch it (pure-logic → unit test; seam → live-drive assertion; human-only → operator checklist line).

## Capabilities

### New Capabilities
- `release-validation`: the `make validate` orchestrator, the `/validate` skill that wraps it, the `FEATURE_MATRIX.md` source of truth, the `UNVERIFIED`/loud-skip reporting contract, the live-drive-over-HTTP layer, the operator checklist, and the maintenance discipline rule that keeps the system in step with fixes and features.

### Modified Capabilities
- `end-to-end-smoke`: add live-drive-over-HTTP scenarios (drive the real daemon, assert `/status` transitions and `/last-transcription`) for both macOS and Linux/X11, and change the reporting contract so an absent device/permission reports `UNVERIFIED` rather than passing silently.

## Impact

- **Code**: new `Makefile` target `validate`; new harness module (e.g. `src/whispy/validation/` or `tests/validation/`) that boots and drives the daemon over HTTP and renders the operator checklist; new `FEATURE_MATRIX.md`; new `.claude/` skill for `/validate`. Extends `tests/test_e2e_smoke.py` and `tests/test_e2e_smoke_linux.py`.
- **Specs/conventions**: update `openspec/specs/TESTING-TIERS.md` — add a `live-driven` tier (real daemon driven over HTTP; unattended; higher trust than `unit-mocked`) and a `linux-real` row alongside `macos-real`.
- **APIs**: consumes the existing HTTP API only; no new endpoints required (may add a read-only health/version field if needed for harness handshake).
- **Dependencies**: none new for the live-drive layer (stdlib HTTP client). Operator layer is interactive terminal only.
- **Platforms**: macOS and Linux/X11 in parity throughout.
- **Risk**: low — additive. The default `make test` is unchanged; `make validate` is opt-in and the loud-skip contract only makes existing silent gaps visible.

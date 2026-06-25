## Context

Whispy is a cross-platform (macOS / Linux-X11) dictation daemon: a trigger key arms an event tap → audio capture → Whisper transcription → text injection into the focused app, with a menu-bar/tray UI. The codebase has ~227 tests, but their trust is uneven (see `openspec/specs/TESTING-TIERS.md`):

- **Default run** (`pytest -m 'not macos and not linux'`) mocks Quartz/rumps/audio in `conftest.py`. Green proves wiring, not real behavior.
- **Real-seam tiers** (`tests/test_e2e_smoke.py`, `tests/test_e2e_smoke_linux.py`, run via `-m macos`/`-m linux`) exercise real mic/event-tap/clipboard/xdotool but `pytest.skip(...)` when a device or permission is absent. An all-skip run looks identical to an all-pass run.
- **`doctor.py`** checks prerequisites (sounddevice, model cache, permissions, daemon presence) but not behavior.

The daemon already exposes an HTTP API (`src/whispy/api/server.py`): `GET /status /config /last-transcription`, `POST /start /stop /stop-async /config`. This is the lever that lets a harness drive and observe the **real** running process without mocks — only the physical keypress and the visual confirmation of injected glyphs remain human-only.

## Goals / Non-Goals

**Goals:**
- One easy-to-trigger entrypoint: `make validate` (portable) + `/validate` skill (triage wrapper).
- Verify real, user-facing behavior on **both** macOS and Linux/X11, not mocked wiring.
- Make absent coverage **visible**: an `UNVERIFIED` outcome distinct from PASS and FAIL.
- A `FEATURE_MATRIX.md` single source of truth mapping every feature → coverage tier → how to verify.
- A maintenance rule that forces the validation system to grow with every fix/feature.

**Non-Goals:**
- Replacing or changing the default `make test` mocked suite (it stays; it is the fast inner loop).
- Synthesizing the physical trigger keypress (CGEvent/xdotool injection of the hotkey itself). Rejected as fragile and permission-heavy; the keypress stays the operator boundary.
- Wayland support (Whispy v1 is X11-only; the harness inherits that constraint).
- CI execution of the live-drive/operator layers — they need real hardware and (for operator) a human. CI keeps running the mocked suite only.

## Decisions

### D1 — Two-faced entrypoint: `make validate` + `/validate` skill
The Make target is the source of truth and runs with zero Claude dependency (CI-adjacent, scriptable, survives tool changes). The `/validate` skill shells out to `make validate`, parses the structured summary, and triages failures (which layer, which feature, likely cause). **Alternative rejected:** skill-only — would lock validation to Claude Code and rot outside it. **Alternative rejected:** make-only — loses the interpret/triage value the user explicitly wanted.

### D2 — Live-drive over the existing HTTP API, no mocks
The harness boots the real daemon (subprocess, real config, real model, real mic), polls `GET /status` for readiness, then drives a record/transcribe cycle via `POST /start` → wait → `POST /stop` (or `/stop-async` + poll), and asserts `GET /last-transcription` is non-empty and well-formed. The conftest Quartz/rumps/audio mocks must NOT be importable here — the harness runs as its own process with real dependencies (mirrors how `test_e2e_smoke.py` already spawns a subprocess for the live event tap). **Alternative rejected:** in-process with real deps — the global mocks in `conftest.py` poison the import graph and macOS frameworks misbehave when re-imported; a clean subprocess is the proven pattern already in the repo.

### D3 — Three outcomes, not two: PASS / FAIL / UNVERIFIED
Every check resolves to exactly one of three states. `UNVERIFIED` = the seam could not be exercised (no mic, permission not granted, `xdotool` absent, daemon wouldn't boot). The run summary prints counts per state and a non-zero, distinct exit signal for UNVERIFIED so it can never be read as success. **Alternative rejected:** pytest-style skip — that is the current silent-pass trap; skips are invisible in a green summary.

### D4 — `FEATURE_MATRIX.md` as the single source of truth
A flat, human-editable table: `Feature | Platform(s) | Tier | Verified by | Notes`. Tier values come from the (extended) TESTING-TIERS convention. The matrix is the index the operator checklist and the live-drive plan are generated/derived from, and the artifact every change must touch. **Alternative rejected:** auto-generating the matrix from test collection — too coupled to pytest, and the human-only `manual-ui` rows have no test to collect. A hand-maintained table is simpler and forces deliberate coverage decisions.

### D5 — Maintenance discipline rule (the "evolves with fixes" requirement)
Encoded in the new capability spec and surfaced in `FEATURE_MATRIX.md`'s header + the `/validate` skill output: any bug fix or feature change MUST (a) update/add the matrix row and (b) add a regression case at the **lowest** tier that can catch it — pure-logic bug → `unit-pure`; seam bug → `live-driven` assertion; human-only bug → `manual-ui` checklist line. This is the mechanism that keeps validation in lockstep with the code instead of decaying.

### D6 — Extend the tier convention
Add `live-driven` to `TESTING-TIERS.md`: real daemon driven over HTTP, unattended, higher trust than `unit-mocked` (proves the real seam) but below the full operator flow (no physical keypress). Add a `linux-real` row alongside `macos-real` so the table reflects both platforms with parity.

### D7 — Operator layer is harness-assisted, not pure paper
For each `manual-ui`/keypress check, the harness prints the exact step, pre-arms what it can (boots daemon, clears `/last-transcription`), and where possible auto-detects the result by polling the API after the human acts — so the human's only job is the physical act and a y/n confirm. Results are recorded to a timestamped run report.

## Risks / Trade-offs

- **Live-drive flakiness from real mic/model** → Use short fixed recordings, generous readiness timeouts, and assert on structural invariants (non-empty transcription, valid state transitions) rather than exact transcript text. Exact-text assertions, if any, live in `transcription-quality`, not here.
- **Daemon boot races / port conflicts** → Reuse the dynamic-port pattern already used by the HTTP API tests; poll `/status` for readiness instead of fixed sleeps.
- **UNVERIFIED fatigue** (everything skips on a misconfigured box) → Preflight (`doctor`) runs first and explains *why* a seam will be UNVERIFIED, so the operator can fix the environment before blaming the app.
- **Matrix drift** (rule ignored under deadline pressure) → The `/validate` output names features whose matrix `Verified by` points at nothing, flagging rows that lost their regression test. Cheap nudge, not enforcement.
- **macOS/Linux divergence in the harness** → Keep platform specifics behind the existing `platform/` abstraction and the per-OS smoke files; the orchestrator selects the OS plan but shares the HTTP-drive core.

## Migration Plan

Additive, no rollback needed. `make test` and CI are untouched. Ship `FEATURE_MATRIX.md` seeded from the current capability specs + smoke tests, the `make validate` target, the live-drive harness, the `/validate` skill, and the TESTING-TIERS update together. Adoption is opt-in: developers run `make validate` before a release or after touching a seam.

## Open Questions

- Does the harness need a tiny read-only `/health` or version field for a clean boot handshake, or is polling `GET /status` sufficient? (Lean: reuse `/status`.)
- Where should the harness live — `tests/validation/` (close to smoke tests, pytest-runnable) or `src/whispy/validation/` (shippable, importable by the skill)? (Lean: `tests/validation/` to keep it out of the shipped package.)
- Should the operator run report be committed (audit trail) or git-ignored (local artifact)? (Lean: git-ignored, with a printed summary.)

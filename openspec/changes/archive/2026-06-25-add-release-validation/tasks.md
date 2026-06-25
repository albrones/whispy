## 1. Conventions & source of truth

- [x] 1.1 Update `openspec/specs/TESTING-TIERS.md`: add a `live-driven` tier row (real daemon driven over HTTP; unattended; trust above `unit-mocked`, below the operator flow) and add a `linux-real` row alongside `macos-real`.
- [x] 1.2 Create `FEATURE_MATRIX.md` at repo root: columns `Feature | Platform(s) | Tier | Verified by | Notes`, seeded from current capability specs + smoke tests, macOS and Linux/X11 in parity. Header states the maintenance discipline rule (D5).
- [x] 1.3 Add a matrix linter check (pure function/test) that flags rows whose `Verified by` target does not exist and rows missing required columns.

## 2. Three-state reporting core

- [x] 2.1 Implement the PASS/FAIL/UNVERIFIED outcome type and a pure summary function (counts per outcome, distinct exit signal when any UNVERIFIED).
- [x] 2.2 Implement skip→UNVERIFIED classification for smoke-tier results (pure mapping).
- [x] 2.3 Unit-test 2.1–2.2 (`unit-pure`): all-pass vs all-unverified produce distinguishable summaries and exit signals.

## 3. Live-drive harness (over HTTP, no mocks)

- [x] 3.1 Create the harness module (decide `tests/validation/` per design open question) that boots the real daemon in a clean subprocess with real dependencies (no conftest Quartz/rumps/audio mocks importable).
- [x] 3.2 Implement readiness polling via `GET /status`, then the drive sequence `POST /start` → wait → `POST /stop` (or `/stop-async` + poll) → `GET /last-transcription`.
- [x] 3.3 Assert valid status transitions and non-empty, well-formed transcription; report UNVERIFIED when mic/model/permission absent. Use dynamic port + readiness poll (no fixed sleeps).
- [x] 3.4 Add the macOS live-drive scenario to `tests/test_e2e_smoke.py` (`-m macos`, tier `live-driven`).
- [x] 3.5 Add the Linux/X11 live-drive scenario to `tests/test_e2e_smoke_linux.py` (`-m linux`, tier `live-driven`; skip Wayland; UNVERIFIED on missing xdotool/X11).

## 4. Preflight layer

- [x] 4.1 Wire `doctor` as the preflight step; for each detected gap, report which downstream checks will be UNVERIFIED and how to remediate.
- [x] 4.2 Stop the flow with an actionable message on a hard-prerequisite FAIL. Unit-test the aggregation with injected results (`unit-mocked`).

## 5. Operator layer

- [x] 5.1 Generate the operator checklist from `FEATURE_MATRIX.md` `manual-ui` rows.
- [x] 5.2 For each item: pre-arm (boot daemon, clear `/last-transcription`), print the exact human step, poll the API to auto-detect the result where possible, prompt PASS/FAIL confirm.
- [x] 5.3 Write a timestamped run report (git-ignored per design lean) and print a summary.

## 6. Entrypoint: make + skill

- [x] 6.1 Add `make validate` target: runs preflight → live-drive (host OS marker) → operator, emits one structured summary with per-feature outcomes and the three-state exit signal.
- [x] 6.2 Ensure `make validate` runs with zero Claude dependency; `make test` and CI remain unchanged.
- [x] 6.3 Add the `/validate` Claude Code skill under `.claude/`: invokes `make validate`, parses the structured summary, triages (layer, feature, likely cause), and surfaces the maintenance rule + any matrix rows whose `Verified by` is missing.

## 7. Validation & docs

- [x] 7.1 Run `openspec validate add-release-validation --strict` and fix any issues.
- [x] 7.2 Run `make validate` on macOS; confirm three-state summary and that absent seams show UNVERIFIED (not pass).
- [x] 7.3 Run `make validate` on a Linux/X11 box (or document the UNVERIFIED result if unavailable here). _No Linux/X11 host available in this session; the Linux live-drive scenario (`tests/test_e2e_smoke_linux.py::TestLiveDriveCycle`) and the harness are platform-symmetric with the verified macOS path and skip cleanly off-Linux. Run `make validate` on a Linux/X11 box to confirm._
- [x] 7.4 Document `make validate` / `/validate` in README + `docs/PROJECT_MAP.md`; cross-link `FEATURE_MATRIX.md` and the maintenance rule.

## 8. Deterministic transcription content (fixtures + /transcribe-file)

- [x] 8.1 Add committed speech fixtures (`tests/fixtures/audio/{fr_speech,en_speech,silence}.wav`) + a reproducible `generate.sh` (macOS `say` → 16 kHz mono).
- [x] 8.2 Add `Engine.transcribe_file(path)` — real model + current config, no inject, no delete; returns `""` for no-speech, `None` only for not-loaded/missing.
- [x] 8.3 Add `POST /transcribe-file` endpoint (200 text / "" empty; 400 missing path; 409 model-not-loaded) + `test_api` coverage.
- [x] 8.4 Add `WHISPY_CONFIG` override to the daemon; harness boots on a throwaway config copy so driving `/config` never mutates the user's file.
- [x] 8.5 Harness `run_semantic_checks`: model-load wait, silence→empty, fr/en known-speech→expected tokens (language honored), `/config` round-trip. Wire into `run_live_drive`.
- [x] 8.6 Add matrix rows (silence, fr, en, language, config-apply, `/transcribe-file`) and operator rows (clipboard, model change, restart, quit). Verify `make validate` shows the new checks PASS on macOS.

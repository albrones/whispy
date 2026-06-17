## Context

Whispy has 8 OpenSpec capabilities and 351 passing tests at 84% core coverage. But the suite hides three blind spots: (1) `tests/conftest.py` mocks `Quartz`, `rumps`, `sounddevice`/`sox`, `WhisperModel`, and `subprocess` globally, so the so-called e2e tests (`test_e2e.py`, `test_event_tap_e2e.py`) actually validate internal orchestration — not real macOS behavior; (2) `core/audio.py` and `core/text_cleaner._HALLUCINATION_PHRASES` implement behaviors no spec describes; (3) some specced scenarios (e.g. core-engine "Restart") have no test at all.

The fix is to make the spec the explicit test perimeter, then classify every scenario by the level at which it can be trusted. `coverage.run.omit` currently excludes `ui/*` and `hardware/event_tap.py` — an implicit admission that those seams are untested. This change makes that explicit and actionable.

## Goals / Non-Goals

**Goals:**
- Give every behavior a spec home (new `audio-capture`, hallucination requirement in `text-cleaning`).
- Define a test-tier vocabulary and tag every scenario with it.
- Produce a scenario→tier matrix that is the direct work-list for steps C, B, A.

**Non-Goals:**
- Writing or modifying any test (steps C/B/A).
- Changing application behavior in `audio.py`, `text_cleaner.py`, or anywhere in `src/`.
- Re-specifying UI, CI, or website capabilities beyond tier annotation.

## Decisions

### Decision: Four test tiers

A scenario is tagged with exactly one tier describing the *highest-fidelity* level at which it is meaningfully verified:

| Tier | Meaning | Runs in CI? | Trust |
|------|---------|-------------|-------|
| `unit-pure` | Pure logic, no OS/hardware/external process. | yes | high — green means correct |
| `unit-mocked` | Orchestration verified with Quartz/sox/Whisper/subprocess mocked. | yes | medium — green proves wiring, not the real seam |
| `macos-real` | Requires a real Mac: event tap, audio device, osascript injection, real Whisper model. | no (local / `@pytest.mark.macos`) | only tier that proves the user-facing behavior |
| `manual-ui` | Menu bar / windows; checked by hand. | no | lowest — no assertion today |

Rationale: a single green/red signal conflates "the logic is right" with "the seam to macOS works". The tier makes the gap explicit so we stop trusting `unit-mocked` greens as proof of real behavior. Alternative considered — coverage % per module — rejected: coverage measures lines hit, not whether the *real* boundary was exercised.

### Decision: Tier lives next to each scenario

Tier is recorded in this matrix (and, at apply time, optionally as a trailing `(tier: macos-real)` note on the scenario in the canonical spec). Keeping it in-spec means the perimeter travels with the requirement instead of in a separate tracking doc that rots.

### Decision: `audio-capture` is its own capability, not folded into core-engine

`core/audio.py` is a distinct module with its own lifecycle (readiness, duration, discard guards). Folding it into `core-engine` would bury the most macos-real-heavy behaviors inside a mostly unit-pure capability. A separate capability keeps the tier distribution legible.

## Scenario → tier matrix

This is the deliverable that scopes C/B/A. ✅ = test exists; ⚠️ = test exists but mocks the real seam; ❌ = no test.

### text-cleaning  (all `unit-pure`)
| Scenario | Tier | Test | State |
|----------|------|------|-------|
| French/English credit stripped, trailing content, whitespace, empty result, no-credit | unit-pure | test_text_cleaning.py | ✅ |
| Hallucination phrase removed mid-text *(new)* | unit-pure | test_text_cleaning.py | ✅ (assert vs new spec) |
| Hallucination-only → empty *(new)* | unit-pure | test_text_cleaning.py | ✅ |
| Longest phrase wins *(new)* | unit-pure | test_text_cleaning.py | ✅ |

### audio-capture  *(new capability)*
| Scenario | Tier | Test | State |
|----------|------|------|-------|
| Duration: valid WAV / unreadable file | unit-pure | test_audio.py | ✅ |
| Short-clip discard / sufficient-length proceeds | unit-mocked | test_audio.py | ✅ |
| Auto-detect too-short warning | unit-mocked | test_audio.py | ✅ |
| Temp-file cleanup present / missing | unit-pure | test_audio.py | ✅ |
| Credit stripping at audio layer / credit-only | unit-pure | test_audio.py | ✅ |
| Transcription failure isolation | unit-mocked | test_audio.py | ✅ |
| Recording readiness: ready / timeout / process-exits | **macos-real** | — | ❌ → **A** (sox + audio device) |

### core-engine
| Scenario | Tier | Test | State |
|----------|------|------|-------|
| Config update triggers reload / default fr / clipboard default / validation filters keys | unit-pure | test_config_validation, test_e2e | ✅ |
| Whisper credit stripped before injection | unit-mocked | test_e2e | ✅ |
| Worker → IDLE on empty / on error | unit-mocked | test_engine | ✅ |
| Custom vocab biases / empty changes nothing / invalid falls back | unit-mocked + unit-pure | test_engine, test_config_validation | ✅ |
| Restart resolves to daemon / any cwd / exits instance | **manual-ui** | — | ❌ → **C** (extract path logic) / manual |

### event-listener
| Scenario | Tier | Test | State |
|----------|------|------|-------|
| Fn press → start / Fn release → stop | **macos-real** | test_event_tap_e2e (Quartz mocked) | ⚠️ → **A** |
| Continuous listening / non-blocking thread | **macos-real** | test_event_tap_e2e (mocked) | ⚠️ → **C** (extract pure keycode/flag logic) + **A** |

### text-injection
| Scenario | Tier | Test | State |
|----------|------|------|-------|
| Successful injection (keystroke) | **macos-real** | test_injection (subprocess mocked) | ⚠️ → **A** |
| Clipboard copy | **macos-real** | test_injection (mocked) | ⚠️ → **A** |
| Quote escaping / empty no-op / mode switch | unit-pure | test_injection | ✅ |

### api-interface  (all `unit-mocked`)
| Scenario | Tier | Test | State |
|----------|------|------|-------|
| /status, /start, /stop, /stop-async, /config, 404 | unit-mocked | test_api/test_server.py | ✅ |

### Missing entirely — semantic layer (step B)
No scenario currently asserts that a *real audio sample in FR/EN produces the expected cleaned text*. This is the gap that answers the user's literal question ("est-ce que les fonctionnalités sont à l'image de ce qu'on a demandé"). It needs a new capability or a cross-cutting `macos-real` requirement set in a later change → **B**.

## How the matrix scopes C / B / A

- **C (cover event-tap / UI):** every `macos-real` row whose logic can be *partially* extracted to `unit-pure` — keycode→name mapping, Fn secondary-flag press/release decoding, restart path resolution, waveform/indicator state. Pull pure logic out of the Quartz/rumps call sites so it becomes CI-testable; the irreducible OS call stays `macos-real`.
- **B (semantic transcription):** the "Missing — semantic layer" gap. Real `tiny` model over fixture `.wav` (FR + EN), assert cleaned output. `macos-real`/local.
- **A (real smoke test):** the remaining `macos-real` rows that no extraction can cover — recording readiness over a real device, real osascript injection, real event tap. One end-to-end `@pytest.mark.macos` flow.

## Risks / Trade-offs

- **Tier drift** → matrix goes stale as code changes. Mitigation: keep the tier inline on the scenario so it's reviewed in the same diff as behavior changes.
- **Over-classifying as `macos-real`** hides logic that could be unit-tested after extraction → fewer cheap tests. Mitigation: step C exists precisely to push `macos-real` rows down to `unit-pure` where extraction is feasible.
- **`unit-mocked` complacency** → teams read green as proof. Mitigation: the tier label itself is the warning; A is mandatory, not optional.

## Apply findings (step D verification)

Verification of the matrix against `src/` and `tests/` (tasks 1.1–1.4):

- **1.1 audio-capture ↔ `audio.py`** — all 7 requirements map to real code (`_wait_for_recording_ready`, `_get_audio_duration`, short-clip discard, auto-detect warning, `cleanup_audio_file`, `strip_whisper_credit`, `transcribe` try/except). Readiness-wait has **no test** — expected (`macos-real`, deferred to A).
- **1.2 text-cleaning hallucination ↔ `text_cleaner.py`** — `_HALLUCINATION_PATTERN` behavior fully covered by `test_text_cleaning.py` (amara, short-form, case-insensitive, embedded, radio-canada, merci).
- **1.3 file-ref correction** — audio-capture duration + auto-detect scenarios are tested in `test_language_detection.py` (not `test_audio.py` as the matrix implied): `test_detects_duration_of_wav_file`, `test_auto_detect_min_duration_config_passed`, `test_transcribe_short_audio_with_auto_does_not_crash`.
- **1.4 mismatch M1 (dead path)** — `language="auto"` is unreachable through real config: `_validate_config` only allows `{fr, en}` and coerces unknown values to `fr`; `engine.run_transcription` always passes the validated config language. So `audio.py`'s auto-detect branch and `auto_detect_min_duration` are effectively dead in production. Decide later (separate change): either expose `"auto"` as a supported language or remove the dead branch. **No code change here.**
- **1.4 mismatch M2 (misleading green)** — `test_language_auto_survives_save_load` mocks `save_config`/`load_config`, bypassing `_validate_config`. It asserts `"auto"` round-trips, but real validation would reject it → `fr`. The green proves nothing about real persistence. Tier = `unit-mocked` but flagged misleading; revisit when M1 is resolved.

## Follow-up change seeds (C → B → A)

Concrete scope derived from the matrix + apply findings, ready to become proposals.

### C — event-tap / UI coverage (extract pure logic, then unit-test)
`macos-real`/`manual-ui` rows whose logic can be pulled out of the OS call site:
- **event-listener**: extract Fn secondary-flag press/release decoding and keycode→name mapping (`event_tap._event_callback`, `_keycode_to_name`) into pure functions → `unit-pure`. The `CGEventTapCreate` + run-loop stays `macos-real` (step A).
- **core-engine / Restart**: extract `whispy_daemon.py` path resolution from the menu-bar click handler → `unit-pure` (covers "resolves to daemon" + "any cwd"). The relaunch + quit stays `manual-ui`.
- **recording-visualization / UI**: extract waveform/indicator/audio-level state computation from rumps/Quartz draw calls → `unit-pure`.
- Side note: also lift the currently-unspecced pure injection behaviors (quote escaping, empty no-op, mode switch) into `text-injection` requirements.

### B — semantic transcription tests (answers "à l'image de ce qu'on a demandé")
The gap no spec covers today: real model output over real audio.
- Fixture `.wav` clips, FR and EN, short and normal length.
- Run the real `tiny` model (CPU int8) and assert the cleaned output matches expected text (exact or fuzzy/WER threshold).
- Cover the custom-vocabulary effect: same clip with/without `initial_prompt`, assert the biased term appears.
- Tier `macos-real`/local (`@pytest.mark.macos`), slow — not CI default.

### A — real end-to-end smoke
The irreducible `macos-real` rows no extraction can cover:
- Real audio device → `sox` recording readiness → real `tiny` model → real `osascript` injection into a focused field, plus a live `CGEventTap` Fn press/release.
- One `@pytest.mark.macos` flow; manual-trigger / local only.

### Step-B capability decision (task 4.4)
Recommendation: give B its own capability **`transcription-quality`** rather than overloading `audio-capture`. Rationale: `audio-capture` specs the *mechanics* (does the pipeline run, are guards applied); semantic correctness ("right words out") is a separate concern with different fixtures and a WER-style acceptance criterion. Keeping them apart preserves the tier legibility this change established. Final call deferred to the B proposal.

## Open Questions

- Should the tier annotation be enforced (lint over spec files) or convention-only? Default: convention-only for now.
- Does step B warrant its own capability (e.g. `transcription-quality`) or live as `macos-real` scenarios under `audio-capture`? Deferred to the B proposal.

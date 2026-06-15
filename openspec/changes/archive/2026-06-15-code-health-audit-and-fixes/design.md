## Context

A parallel multi-dimensional review (bugs, security, dead code, architecture, performance, missing tests) was run over `src/whispy` (~2.7k LOC). It produced many findings of varying confidence. This change captures all of them in a durable report and lands only the fixes that are confirmed by reading the code and are low-risk. Larger structural items (API auth, dedup of stop/transcribe orchestration, dead-code removal, perf of the dual mic capture) are recorded in the report as follow-up, not done here, to keep this change small and verifiable.

## Goals / Non-Goals

**Goals:**
- Durable, categorized audit report under `docs/`.
- Fix the three confirmed, low-risk bugs with tests.

**Non-Goals:**
- API authentication / DNS-rebinding hardening (recorded as follow-up).
- Refactoring `_sync_stop_and_transcribe` to share a single engine path.
- Removing dead code (`IndicatorWindow`, `play_sound`, vestigial `DictationState` fields) — recorded as follow-up; removal touches tests and UI and deserves its own change.
- Performance work (dual mic capture, idle timers, the 150 ms sleep).

## Decisions

### Worker FSM completion (engine.py)
Today: `text = run_transcription(); if text: transcription_complete()`. Problem: empty/hallucination-only output and exceptions both skip completion; an exception also kills the worker thread (`_transcription_running` stays True, FSM stuck in `TRANSCRIBING`).

Fix: wrap `run_transcription()` in try/except (log on error) and call `self._state_machine.transcription_complete()` unconditionally in a `finally`. `transcription_complete()` is already safe to call when not in `TRANSCRIBING` — it returns `False` without raising (`state_machine.py:162`) — so unconditional completion is harmless in the no-op case. The success "Pop" sound stays gated on a successful transcription so failures don't sound like success.

### `/stop-async` fix (server.py)
`engine.state._stop_event.set()` → `engine.state.stop_event.set()`. The attribute is `stop_event` (`engine.py:102`); `_stop_event` never existed, so the read raised `AttributeError` → HTTP 500.

### `copy_to_clipboard` default (engine.py)
`state.config.get("copy_to_clipboard", True)` → `... , False)`. Matches `DEFAULT_CONFIG` and the existing `core-engine` spec scenario "Default copy to clipboard is disabled". In practice `state.config` is seeded from `DEFAULT_CONFIG` so the key is present; the fix removes the contradictory fallback for the empty-config path.

## Risks / Trade-offs

- Unconditional `transcription_complete()` in the worker: safe because the FSM no-ops the transition when not in `TRANSCRIBING`. Verified against `state_machine.py`.
- Scope discipline: many real findings are intentionally deferred. The report makes them explicit so they are not lost.

## Migration Plan

Pure bug fixes; no config, API-shape, or data migration. Existing callers of `/stop-async` that previously received a 500 now get a 200.

## Open Questions

- Whether API auth is warranted given the `127.0.0.1` bind — deferred to a dedicated security change; captured in the report.

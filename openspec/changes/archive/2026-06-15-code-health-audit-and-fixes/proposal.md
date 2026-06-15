## Why

The codebase has never had a consolidated health review. A multi-dimensional analysis (bugs, dead code, missing tests, architecture, performance, security) surfaced several confirmed defects — most notably a broken `/stop-async` endpoint and a transcription worker that can wedge the state machine. We want a written audit that records every finding for future work, and we want to fix the highest-confidence, lowest-risk bugs now (with tests), rather than leaving known breakage in shipped code.

## What Changes

- Add `docs/code-audit.md` — a categorized audit report (bugs / dead code / missing tests / architecture / performance / security) with severity, location, and recommendation for each finding. This is the durable artifact future changes draw from.
- Fix three confirmed bugs surfaced by the audit:
  - **`/stop-async` is broken**: `server.py` calls `engine.state._stop_event.set()`, but the attribute is `stop_event`. The read of the nonexistent `_stop_event` raises `AttributeError`, so the endpoint returns HTTP 500 and never signals the worker. Fix to `engine.state.stop_event`.
  - **Transcription worker can wedge the FSM**: the worker only calls `transcription_complete()` when `run_transcription()` returns truthy text and does not guard against exceptions. An empty/hallucinated transcription (cleaned to `""`) or a raised exception leaves the FSM stuck in `TRANSCRIBING` (and can kill the worker thread). Always return the FSM to `IDLE` and guard the transcription call.
  - **`copy_to_clipboard` default mismatch**: the `TextInjector` is built with a `True` fallback (`engine.py:142`) while `DEFAULT_CONFIG["copy_to_clipboard"]` and the `core-engine` spec say the default is `False`. Align the fallback to `False`.
- Add unit tests covering each fix.

## Capabilities

### Modified Capabilities
- `api-interface`: the `/stop-async` endpoint SHALL signal the transcription worker via the engine's public stop event and return success (no longer error).
- `core-engine`: the transcription worker SHALL always return the FSM to `IDLE` after a stop signal — including when transcription yields no text or raises — so the system never wedges in `TRANSCRIBING`.

## Impact

- `docs/code-audit.md` — new audit report (all findings).
- `src/whispy/api/server.py` — fix `_stop_event` → `stop_event`.
- `src/whispy/core/engine.py` — worker always completes FSM + guards exceptions; `copy_to_clipboard` fallback `True` → `False`.
- `tests/` — add tests for `/stop-async`, worker FSM completion on empty/raising transcription, and the clipboard default.

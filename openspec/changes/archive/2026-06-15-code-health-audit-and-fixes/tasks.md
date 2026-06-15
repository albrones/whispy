## 1. Write the audit report

- [x] 1.1 Create `docs/code-audit.md` with sections: Bugs, Security, Dead code, Architecture, Performance, Missing tests
- [x] 1.2 For each finding record severity, `file:line`, problem, and recommendation; mark which are fixed in this change vs. deferred follow-up

## 2. Fix /stop-async (server.py)

- [x] 2.1 Change `engine.state._stop_event.set()` to `engine.state.stop_event.set()`

## 3. Fix transcription worker FSM completion (engine.py)

- [x] 3.1 Wrap `run_transcription()` in try/except in the worker, logging on error
- [x] 3.2 Call `transcription_complete()` unconditionally (finally) so empty/erroring transcriptions still return the FSM to IDLE
- [x] 3.3 Keep the success sound gated on a successful (truthy) transcription

## 4. Fix copy_to_clipboard default (engine.py)

- [x] 4.1 Change the `TextInjector` fallback from `True` to `False` to match `DEFAULT_CONFIG`

## 5. Add unit tests

- [x] 5.1 Test that POST `/stop-async` returns 200 `{"status": "stopping"}` and sets the engine stop event (regression test for the `_stop_event` bug)
- [x] 5.2 Test that the worker returns the FSM to IDLE when transcription yields no text
- [x] 5.3 Test that the worker returns the FSM to IDLE (and survives) when transcription raises
- [x] 5.4 Test that the `TextInjector` clipboard default is `False` when config lacks the key

## 6. Verification

- [x] 6.1 Run the full test suite; confirm no regression
- [x] 6.2 `ruff check` / `ruff format --check` on changed files
- [x] 6.3 `openspec validate code-health-audit-and-fixes --strict`

## Context

The E2E test suite has 10 failures and 2 hangs across two test files. All failures are in test infrastructure — no production code is broken. The tests exercise the full recording → transcription → injection workflow with mocked subprocess calls.

## Goals / Non-Goals

**Goals:**
- Make all 85 E2E tests (42 in `test_e2e.py` + 43 in `test_event_tap_e2e.py`) pass reliably
- Fix mock paths so `subprocess.run` and `subprocess.Popen` are properly intercepted
- Fix HTTPServer fixture to correctly wire the engine instance

**Non-Goals:**
- No production code changes
- No new test cases
- No changes to test architecture or framework

## Decisions

### Decision 1: Fix TextInjector mock path
`TextInjector` imports `subprocess` at module level. `mocker.patch("subprocess.run")` patches the global, but the module already holds a reference. Fix: patch at `whispy.hardware.injection.subprocess.run`.

### Decision 2: Fix HTTPServer engine attribute
The fixture sets `RequestHandler.engine = engine` (class attribute on `BaseHTTPRequestHandler`), but `do_GET`/`do_POST` access `self.server.engine` (instance attribute on `HTTPServer`). Fix: set `server.engine = engine` on the `HTTPServer` instance.

### Decision 3: Fix AudioEngine hang
`AudioEngine.start()` creates a `subprocess.Popen` for sox, then calls `_wait_for_recording_ready()` which polls `self._recording_process.poll()`. If `poll()` returns a truthy value, the poll loop exits without setting the `ready` event, causing an indefinite hang. Fix: ensure the mock Popen instance has `poll.return_value = None` (process still running) so the ready event fires when file size exceeds threshold.

## Risks / Trade-offs

[Risk] Mocking `subprocess.Popen` to return `poll() = None` means the sox process appears alive forever.
→ Mitigation: The mock doesn't actually spawn a process; the tests use pre-written WAV files. The poll mock just needs to return `None` to keep the readiness loop running until the file size check passes.

[Risk] Widely patching `subprocess.run` could affect other tests in the same session.
→ Mitigation: Each test that needs subprocess mocking uses its own fixture with scoped patching via `with patch(...)` or fixture-level patching.

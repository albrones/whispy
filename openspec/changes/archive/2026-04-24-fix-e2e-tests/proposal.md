## Why

The E2E test suite (`tests/test_e2e.py` and `tests/test_event_tap_e2e.py`) has 10 failing tests and 2 hanging tests that prevent verifying the full recording → transcription → injection workflow. The failures are in `TestTextInjector` (mock path mismatch) and `TestHTTPAPIWithEngine` (HTTPServer attribute access), while the hangs are caused by `AudioEngine._wait_for_recording_ready()` blocking indefinitely when `subprocess.Popen` is mocked.

## What Changes

- Fix `TestTextInjector` tests to mock `subprocess.run` at the correct import path (`whispy.hardware.injection.subprocess.run`)
- Fix `TestHTTPAPIWithEngine` fixture to set `server.engine` (instance attribute on `HTTPServer`) instead of `RequestHandler.engine` (class attribute on `BaseHTTPRequestHandler`)
- Fix `TestFullWorkflow` and `TestFullFnWorkflowIntegration` tests to properly mock `subprocess.Popen` return value so `poll()` returns `None` (process still running) during `_wait_for_recording_ready()` polling
- Ensure all 42 tests in `test_e2e.py` and 43 tests in `test_event_tap_e2e.py` pass

## Capabilities

### New Capabilities
- `e2e-test-fixes`: Fixes for E2E test infrastructure covering TextInjector mocking, HTTPServer attribute wiring, and AudioEngine recording readiness polling

### Modified Capabilities
- None — no spec-level requirement changes, only test infrastructure fixes

## Impact

- `tests/test_e2e.py` — fix 10 failures + 2 hangs
- `tests/test_event_tap_e2e.py` — fix 25 hangs in `TestFullFnWorkflowIntegration`
- No production code changes required

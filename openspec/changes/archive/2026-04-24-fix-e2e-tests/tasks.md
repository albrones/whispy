## 1. Fix TextInjector mock paths

- [x] 1.1 Update `TestTextInjector.test_inject_via_clipboard` to patch `whispy.hardware.injection.subprocess.run` instead of global `subprocess.run`
- [x] 1.2 Update `TestTextInjector.test_inject_via_keystrokes` to patch `whispy.hardware.injection.subprocess.run`
- [x] 1.3 Update `TestTextInjector.test_inject_with_quotes_escapes_them` to patch `whispy.hardware.injection.subprocess.run`

## 2. Fix HTTPServer engine attribute wiring

- [x] 2.1 Update `TestHTTPAPIWithEngine.test_server` fixture to set `server.engine = engine` on the HTTPServer instance
- [x] 2.2 Verify all 7 HTTP API tests pass

## 3. Fix AudioEngine._wait_for_recording_ready() hangs

- [x] 3.1 Update `TestFullWorkflow` fixture or test methods to configure `mock_popen.poll.return_value = None` so the readiness polling loop completes
- [x] 3.2 Verify `test_complete_workflow_with_mocked_audio` completes without hanging
- [x] 3.3 Verify `test_workflow_with_clipboard_disabled` completes without hanging

## 4. Fix EventTap E2E hangs

- [x] 4.1 Update `TestFullFnWorkflowIntegration` tests to configure `mock_popen.poll.return_value = None` where `engine.start_recording()` is called
- [x] 4.2 Verify all 25 `TestFullFnWorkflowIntegration` tests complete without hanging

## 5. Verify full suite

- [x] 5.1 Run `python -m pytest tests/test_e2e.py -v` and confirm 42/42 pass
- [x] 5.2 Run `python -m pytest tests/test_event_tap_e2e.py -v` and confirm 43/43 pass

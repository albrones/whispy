# Whispy E2E Test Plan

This plan breaks down end-to-end testing into sequential, actionable tasks.
Each task is designed to be executed by a sub-agent in isolation.

## Session 0: Prerequisites

- [x] Verify test environment: `python -m pytest --collect-only`
- [x] Ensure 182 existing tests still pass: `python -m pytest`
- [x] Fix the 2 remaining failing TestFullWorkflow tests in `tests/test_e2e.py`

---

## Task 1: Engine Initialization & Config Loading

- [x] All tests pass: `TestEngineLifecycle`, `TestConfigPersistence`

**Goal:** Verify Engine creates correctly with default and custom configs.

**Test classes to validate:**
- `TestEngineLifecycle.test_engine_initial_state`
- `TestEngineLifecycle.test_engine_config_update`
- `TestEngineLifecycle.test_engine_config_update_returns_reload_flag`
- `TestEngineLifecycle.test_engine_text_injector_config_sync`
- `TestConfigPersistence.test_save_and_load_config`
- `TestConfigPersistence.test_load_missing_config_falls_back_to_defaults`
- `TestConfigPersistence.test_load_corrupted_config_falls_back_to_defaults`
- `TestConfigPersistence.test_config_partial_update`
- `TestConfigPersistence.test_save_config_uses_passed_path_not_hardcoded`
- `TestConfigPersistence.test_engine_update_config_persists`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestEngineLifecycle tests/test_e2e.py::TestConfigPersistence -v
```

---

## Task 2: State Machine Transitions

- [x] All tests pass: `TestFSMWithAudioEngine`

**Goal:** Verify FSM state transitions are correct and trackable.

**Test classes to validate:**
- `TestFSMWithAudioEngine.test_full_recording_cycle_via_audio_engine`
- `TestFSMWithAudioEngine.test_cannot_double_start`
- `TestFSMWithAudioEngine.test_cannot_stop_when_idle`
- `TestFSMWithAudioEngine.test_audio_engine_properties_track_fsm`
- `TestFSMWithAudioEngine.test_fsm_transition_history`
- `TestFSMWithAudioEngine.test_fsm_callbacks_invoked_on_transitions`
- `TestFSMWithAudioEngine.test_engine_fsm_state_sync`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestFSMWithAudioEngine -v
```

---

## Task 3: TextInjector (Both Modes)

- [x] All tests pass: `TestTextInjector`

**Goal:** Verify text injection works in clipboard and keystroke modes.

**Test classes to validate:**
- `TestTextInjector.test_inject_via_clipboard`
- `TestTextInjector.test_inject_via_keystrokes`
- `TestTextInjector.test_inject_empty_text_does_nothing`
- `TestTextInjector.test_inject_with_quotes_escapes_them`
- `TestTextInjector.test_update_config_changes_mode`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestTextInjector -v
```

---

## Task 4: HTTP API Server

- [x] All tests pass: `TestHTTPAPIWithEngine`

**Goal:** Verify all HTTP endpoints work with a real Engine instance.

**Test classes to validate:**
- `TestHTTPAPIWithEngine.test_get_status_returns_engine_status`
- `TestHTTPAPIWithEngine.test_get_config_returns_config`
- `TestHTTPAPIWithEngine.test_post_config_updates_and_persists`
- `TestHTTPAPIWithEngine.test_get_last_transcription`
- `TestHTTPAPIWithEngine.test_post_start_triggers_recording`
- `TestHTTPAPIWithEngine.test_post_stop_with_transcription`
- `TestHTTPAPIWithEngine.test_unknown_endpoint_returns_404`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestHTTPAPIWithEngine -v
```

---

## Task 5: COMPUTE_OPTIONS Structure

- [x] All tests pass: `TestComputeOptions`

**Goal:** Verify compute options have the required keys and valid values.

**Test classes to validate:**
- `TestComputeOptions.test_all_options_have_label`
- `TestComputeOptions.test_all_options_have_device`
- `TestComputeOptions.test_all_options_have_compute_type`
- `TestComputeOptions.test_labels_are_human_readable`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestComputeOptions -v
```

---

## Task 6: Engine + AudioEngine + FSM Integration

- [x] All tests pass: `TestFullEngineAudioFSMIntegration`

**Goal:** Verify the three core components work together correctly.

**Test classes to validate:**
- `TestFullEngineAudioFSMIntegration.test_engine_start_recording_via_audio`
- `TestFullEngineAudioFSMIntegration.test_engine_stop_recording_via_audio`
- `TestFullEngineAudioFSMIntegration.test_engine_cannot_double_start`
- `TestFullEngineAudioFSMIntegration.test_engine_transcription_worker_config`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestFullEngineAudioFSMIntegration -v
```

---

## Task 7: Full Workflow (Recording -> Transcription -> Injection)

- [x] All tests pass: `TestFullWorkflow`

**Goal:** Verify the complete user-facing workflow end-to-end.

**Test classes to validate:**
- `TestFullWorkflow.test_complete_workflow_with_mocked_audio`
- `TestFullWorkflow.test_workflow_with_clipboard_disabled`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestFullWorkflow -v
```

---

## Task 8: Status Callbacks & Notifications

- [x] All tests pass: `TestEngineLifecycle` (callback/fsm_dict tests)

**Goal:** Verify status change callbacks are invoked correctly.

**Test classes to validate (from TestEngineLifecycle):**
- `TestEngineLifecycle.test_engine_status_callbacks`
- `TestEngineLifecycle.test_multiple_status_callbacks`
- `TestEngineLifecycle.test_engine_get_status_fsm_dict`

**Verification command:**
```bash
python -m pytest tests/test_e2e.py::TestEngineLifecycle -k "callback or fsm_dict" -v
```

---

## Execution Order

Run tasks in this order for maximum isolation:

1. **Task 1** - Engine Initialization & Config (foundation)
2. **Task 5** - COMPUTE_OPTIONS (simple validation, no side effects)
3. **Task 2** - State Machine (core logic, no external deps)
4. **Task 3** - TextInjector (isolated, mocked subprocess)
5. **Task 4** - HTTP API (uses real Engine, port-scoped)
6. **Task 6** - Engine + AudioEngine + FSM (integration layer)
7. **Task 8** - Status Callbacks (notification layer)
8. **Task 7** - Full Workflow (complete end-to-end, depends on all above)

---

## Success Criteria

- [x] All 227 tests pass (182 original + 45 new E2E tests + event tap tests)
- [x] All E2E test classes pass
- [x] 0 regressions in all test files
- [x] 81% code coverage on core modules

## Notes

- Each task should be run in isolation to catch environment pollution
- If a task fails, fix the root cause before proceeding to the next task
- The `mock_subprocess` and `mock_whisper_model` fixtures provide necessary isolation
- HTTP API tests use dynamic port assignment to avoid conflicts

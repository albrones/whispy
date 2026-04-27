## 1. Test Infrastructure Setup

- [x] 1.1 Add pytest, pytest-cov, pytest-mock to dev dependencies in project
- [x] 1.2 Create `tests/conftest.py` with shared fixtures (mock Engine, mock config, temp dirs)
- [x] 1.3 Create `pytest.ini` or `pyproject.toml` pytest config (testpaths, markers, coverage)
- [x] 1.4 Create `tests/__init__.py` and `tests/test_placeholder.py` removal

## 2. State Machine Tests

- [x] 2.1 Create `tests/test_state_machine.py`
- [x] 2.2 Test valid transition chain (IDLE → RECORDING → TRANSCRIBING → IDLE)
- [x] 2.3 Test all illegal transitions raise InvalidTransitionError
- [x] 2.4 Test callback invocation order and content
- [x] 2.5 Test thread safety with concurrent transitions (port existing stress tests)
- [x] 2.6 Test transition history tracking
- [x] 2.7 Test `start_recording()`, `stop_recording()`, `transcription_complete()` convenience methods
- [x] 2.8 Test `to_dict()` output format

## 3. Engine & Config Tests

- [x] 3.1 Create `tests/test_engine.py`
- [x] 3.2 Test `load_config` with valid config file
- [x] 3.3 Test `load_config` with missing config file (fallback to defaults)
- [x] 3.4 Test `load_config` with corrupted JSON (fallback to defaults)
- [x] 3.5 Test `load_config` with partial config (only some keys)
- [x] 3.6 Test `save_config` writes correct JSON to disk
- [x] 3.7 Test `save_config` creates directory if missing
- [x] 3.8 Test `Engine.get_status()` returns correct initial state
- [x] 3.9 Test `Engine.on_status_change` callback notification
- [x] 3.10 Test `Engine.update_config` applies updates and saves
- [x] 3.11 Test `Engine.update_config` returns True when model_size changes
- [x] 3.12 Test `Engine.update_config` returns False when only copy_to_clipboard changes

## 4. Text Injection Tests

- [x] 4.1 Create `tests/test_injection.py`
- [x] 4.2 Test clipboard injection mode (mock subprocess.run)
- [x] 4.3 Test keystroke injection mode (mock subprocess.run)
- [x] 4.4 Test empty/None text does not call subprocess
- [x] 4.5 Test double quote escaping in osascript commands
- [x] 4.6 Test `update_config` changes injection mode

## 5. Audio Engine Tests

- [x] 5.1 Create `tests/test_audio.py`
- [x] 5.2 Test `AudioEngine.start()` transitions FSM to RECORDING
- [x] 5.3 Test `AudioEngine.start()` returns False when already recording
- [x] 5.4 Test `AudioEngine.stop()` terminates subprocess and transitions FSM
- [x] 5.5 Test `AudioEngine.stop()` returns False when not recording
- [x] 5.6 Test `cleanup_audio_file()` removes existing file
- [x] 5.7 Test `cleanup_audio_file()` does not error on missing file
- [x] 5.8 Test `transcribe()` with None model returns None
- [x] 5.9 Test `transcribe()` with valid model calls WhisperModel.transcribe correctly
- [x] 5.10 Test language parameter is passed through to WhisperModel

## 6. HTTP API Tests

- [x] 6.1 Create `tests/test_api/` directory with `__init__.py` and `conftest.py`
- [x] 6.2 Create `tests/test_api/test_server.py`
- [x] 6.3 Test GET /status returns 200 with engine status dict
- [x] 6.4 Test GET /config returns 200 with config dict
- [x] 6.5 Test GET /last-transcription returns 200 with text
- [x] 6.6 Test POST /config updates config and returns new config
- [x] 6.7 Test POST /config with invalid JSON returns 400
- [x] 6.8 Test POST /start and /stop endpoints
- [x] 6.9 Test unknown GET path returns 404
- [x] 6.10 Test unknown POST path returns 404

## 7. Integration Tests

- [x] 7.1 Create `tests/test_integration.py`
- [x] 7.2 Test full Engine lifecycle (start → config update → status check → stop)
- [x] 7.3 Test Engine + AudioEngine + StateMachine integration
- [x] 7.4 Test Engine + TextInjector integration
- [x] 7.5 Test concurrent config updates are safe

## 8. Auto-Detect Language Fix

- [x] 8.1 Investigate exact failure mode: add language detection logging to `~/.whispy-error.log`
- [x] 8.2 Add `auto_detect_min_duration` config option to `DEFAULT_CONFIG` (default: 0.5)
- [x] 8.3 Update `_build_menu()` in `menu_bar.py` to expose auto-detect duration setting
- [x] 8.4 Update `AudioEngine.transcribe()` to handle short audio with auto-detect
- [x] 8.5 Detect audio file duration before transcription using `sox` or `wave` module
- [x] 8.6 If duration < threshold and language="auto", log warning and proceed with best effort
- [x] 8.7 Update `SUPPORTED_LANGUAGES` to document auto-detect behavior

## 9. Regression Tests for Auto-Detect Fix

- [x] 9.1 Create `tests/test_language_detection.py`
- [x] 9.2 Test `transcribe()` with language="auto" passes parameter correctly
- [x] 9.3 Test audio duration detection works for short files
- [x] 9.4 Test config persistence for language value across save/load cycles
- [x] 9.5 Test short audio (< 1s) is handled gracefully

## 10. Cleanup & Verification

- [x] 10.1 Run `pytest` and verify all tests pass
- [x] 10.2 Run `pytest --cov=src/whispy` and verify coverage report
- [x] 10.3 Remove old `src/whispy/core/test_core.py` and `test_stress.py` (moved to tests/)
- [x] 10.4 Update README with test instructions
- [x] 10.5 Verify tests run on non-macOS platforms (mocked deps)

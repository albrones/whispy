## Context

Whispy is a macOS menu bar speech-to-text daemon (~600 lines across 8 modules). It currently has minimal tests: only `test_core.py` (7 assertions-style tests) and `test_stress.py` (6 threading tests) living inside `src/whispy/core/`. The `tests/unit/` directory is a placeholder. Users have reported bugs (auto-detect language not working) that would be caught by a proper test suite.

The app has a clear architecture: Engine orchestrates StateMachine → AudioEngine → WhisperModel, with separate layers for hardware (event_tap, injection), UI (menu_bar), and API (server).

## Goals / Non-Goals

**Goals:**
- Add pytest-based test suite covering all pure-Python modules
- Fix the auto-detect language bug with a targeted solution
- Add regression tests for the fix
- Enable running tests without macOS hardware (mock hardware layer)

**Non-Goals:**
- Testing macOS-specific code (CGEventTap, rumps UI) on non-macOS
- Testing actual Whisper transcription accuracy
- Testing actual audio recording (sox integration)
- Testing actual text injection (osascript)
- CI/CD pipeline setup (future change)

## Decisions

### Decision 1: pytest with pytest-mock over unittest
**Choice:** Use pytest with `pytest-mock` for fixtures and mocking.

**Rationale:**
- pytest has superior test discovery (`tests/**/test_*.py`)
- `pytest-mock` provides clean `unittest.mock` integration
- Fixtures reduce setup boilerplate (shared mocks for Engine, config, etc.)
- `pytest-cov` for coverage reporting

**Alternatives considered:**
- `unittest` — built-in but verbose, no test discovery
- Custom assertion runners — no coverage, no reporting

### Decision 2: Mock strategy for macOS deps
**Choice:** Mock `Quartz` and `rumps` modules at the test level using `sys.modules` patching.

**Approach:**
```python
# conftest.py or test fixture
@pytest.fixture(autouse=True)
def mock_macos_deps():
    sys.modules['Quartz'] = MagicMock()
    sys.modules['rumps'] = MagicMock()
```

**Rationale:**
- Allows running all tests on any platform
- Hardware code paths can still be tested with mocked Quartz events
- UI code can be tested with mocked rumps components

### Decision 3: Test directory structure
**Choice:** Mirror source structure under `tests/`:
```
tests/
├── conftest.py           ← Shared fixtures (mock Engine, config)
├── test_engine.py        ← Engine, DictationState, config
├── test_state_machine.py ← FSM transitions, callbacks, thread safety
├── test_audio.py         ← AudioEngine with mocked subprocess
├── test_injection.py     ← TextInjector with mocked subprocess
├── test_api/
│   ├── conftest.py       ← HTTP server fixtures
│   └── test_server.py    ← HTTP endpoints
└── test_integration.py   ← Multi-module integration tests
```

**Rationale:**
- Intuitive mapping from source to test
- Easy to find tests for a given module
- Scales as the project grows

### Decision 4: Auto-detect language fix approach
**Choice:** Add an `auto_detect_min_duration` config option (default: 0.5s) that pads the beginning of short recordings before transcription.

**Root cause analysis:**
The bug likely stems from one of two issues:
1. **Short audio segments**: `faster-whisper` needs ~1-2 seconds of speech for reliable language detection. Fn key press-and-release often produces very short recordings.
2. **Silence at start**: If the first 500ms is silence (user hasn't started speaking yet), the model may detect the wrong language from background noise.

**Approach:**
- Add `auto_detect_min_duration` to config (default: 0.5)
- In `AudioEngine.transcribe()`, if language is "auto" and audio duration < threshold, pad with silence or use a preamble buffer
- Alternatively: detect audio duration before transcription and skip auto-detect for very short clips (< 0.5s), falling back to a default language

**Decision:** Use a hybrid approach:
1. Detect audio file duration before transcription
2. If duration < 1.0s and language="auto", add a small delay hint or use the `initial_prompt` to guide detection
3. Log the detected language for debugging

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Mocking Quartz/rumps may not catch real bugs | Accept trade-off; hardware tests run on macOS manually |
| Audio padding may add latency | Configurable threshold; default 0.5s is imperceptible |
| New tests may expose more bugs than expected | Scope fix to auto-detect; log other bugs for future changes |
| `faster-whisper` auto-detect may have inherent limits | Document known limitations; add config to override when needed |

## Open Questions

1. **What is the exact failure mode of the auto-detect bug?** — We need more info: recording length, language pair (e.g., French→English?), error pattern (gibberish vs. wrong language).
2. **Should we add a `language_detection_log` to `~/.whispy-error.log`?** — Would help diagnose future auto-detect issues.
3. **Should the test suite run in CI?** — Out of scope, but `pytest` setup makes it easy to add later.

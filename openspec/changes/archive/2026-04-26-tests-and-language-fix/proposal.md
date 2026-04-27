## Why

Whispy lacks automated tests, making it fragile to changes and blind to regressions. Users have reported specific bugs (e.g., auto-detect language mode not working) that would be caught by a test suite. The codebase has grown to ~600 lines across multiple modules but has only placeholder tests in `tests/unit/`.

## What Changes

- Add pytest as a dev dependency with a proper test suite
- Write unit tests for all pure-Python modules: `state_machine`, `engine` (config), `audio`, `injection`, `api/server`
- Mock macOS-only dependencies (`Quartz`, `rumps`) to enable CI-friendly testing
- Fix the auto-detect language bug (likely related to short audio segments or `faster-whisper` behavior with `language="auto"`)
- Add regression tests for the language detection fix
- Address known code quality issues found during code review

## Capabilities

### New Capabilities
- `testing`: Automated test suite with pytest covering core logic, state machine, config, text injection, and HTTP API
- `language-detection`: Reliable auto-detect language mode with proper handling of short audio segments

### Modified Capabilities
- None yet (existing config and transcription behavior will be refined)

## Impact

- **Code**: `src/whispy/core/`, `src/whispy/hardware/`, `src/whispy/api/`, `src/whispy/ui/`
- **Dependencies**: Add `pytest`, `pytest-cov`, `pytest-mock` as dev dependencies
- **API**: No breaking changes to HTTP API or config format
- **Config**: May add new config keys for language detection behavior (e.g., `auto_detect_min_duration`)

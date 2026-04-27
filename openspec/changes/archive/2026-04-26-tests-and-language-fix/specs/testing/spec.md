## ADDED Requirements

### Requirement: Core engine tests
The test suite MUST cover all pure-Python core engine logic including state machine transitions, config loading/saving, and engine status reporting.

#### Scenario: Valid state transitions
- **WHEN** the state machine transitions through IDLE → RECORDING → TRANSCRIBING → IDLE
- **THEN** all transitions succeed and the final state is IDLE

#### Scenario: Invalid state transitions are rejected
- **WHEN** an illegal transition is attempted (e.g., IDLE → TRANSCRIBING)
- **THEN** `InvalidTransitionError` is raised and state remains unchanged

#### Scenario: Config loads from disk with fallback to defaults
- **WHEN** `load_config` is called with an existing config file
- **THEN** saved values override defaults

#### Scenario: Config saves correctly
- **WHEN** `save_config` is called with a config dict
- **THEN** the file is written with all keys and the directory is created if needed

### Requirement: Text injection tests
The test suite MUST cover the `TextInjector` class with mocked subprocess calls.

#### Scenario: Clipboard injection mode
- **WHEN** `inject()` is called with `copy_to_clipboard=True`
- **THEN** `subprocess.run` is called with the clipboard osascript command

#### Scenario: Keystroke injection mode
- **WHEN** `inject()` is called with `copy_to_clipboard=False`
- **THEN** `subprocess.run` is called with the keystroke osascript command

#### Scenario: Empty text is ignored
- **WHEN** `inject()` is called with empty or None text
- **THEN** no subprocess call is made

#### Scenario: Special characters are escaped
- **WHEN** `inject()` is called with text containing double quotes
- **THEN** the text is properly escaped in the osascript command

### Requirement: HTTP API tests
The test suite MUST cover the HTTP API endpoints with mocked dependencies.

#### Scenario: GET /status returns engine status
- **WHEN** a GET request is sent to `/status`
- **THEN** the response contains the engine status dict with correct fields

#### Scenario: GET /config returns current config
- **WHEN** a GET request is sent to `/config`
- **THEN** the response contains the current config dict

#### Scenario: POST /config updates config
- **WHEN** a POST request is sent to `/config` with a JSON body
- **THEN** the config is updated and the new config is returned

#### Scenario: Unknown endpoint returns 404
- **WHEN** a GET or POST request is sent to an unknown path
- **THEN** the response is 404 with an error message

### Requirement: Audio engine tests
The test suite MUST cover the `AudioEngine` class with mocked subprocess calls.

#### Scenario: Recording start transitions FSM
- **WHEN** `start()` is called on an idle AudioEngine
- **THEN** the FSM transitions to RECORDING and a subprocess is spawned

#### Scenario: Recording stop cleans up process
- **WHEN** `stop()` is called while recording
- **THEN** the subprocess is terminated and FSM transitions to TRANSCRIBING

#### Scenario: Cleanup removes audio file
- **WHEN** `cleanup_audio_file()` is called on an existing file
- **THEN** the file is removed from disk

#### Scenario: Transcription with no model returns None
- **WHEN** `transcribe()` is called with a None model
- **THEN** None is returned

### Requirement: Test infrastructure
The test suite MUST be runnable with `pytest` from the project root with no macOS dependencies required for core tests.

#### Scenario: Run all tests
- **WHEN** `pytest` is run from the project root
- **THEN** all tests pass and report coverage

#### Scenario: Tests mock macOS-only deps
- **WHEN** tests import `event_tap` or `menu_bar`
- **THEN** macOS dependencies are mocked and tests run on non-macOS platforms

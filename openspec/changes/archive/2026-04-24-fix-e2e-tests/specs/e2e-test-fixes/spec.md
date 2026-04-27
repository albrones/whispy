## ADDED Requirements

### Requirement: TextInjector subprocess mock must intercept at module path
The test for `TextInjector` SHALL patch `subprocess.run` at the import path where `whispy.hardware.injection` imports it, ensuring the mock is seen by the module.

#### Scenario: Clipboard mode inject calls subprocess.run
- **WHEN** `TextInjector(copy_to_clipboard=True).inject("text")` is called with `subprocess.run` patched at `whispy.hardware.injection.subprocess.run`
- **THEN** the mock's `call_count` is 1 and the command contains `osascript`

#### Scenario: Keystroke mode inject calls subprocess.run
- **WHEN** `TextInjector(copy_to_clipboard=False).inject("text")` is called with `subprocess.run` patched at `whispy.hardware.injection.subprocess.run`
- **THEN** the mock's `call_count` is 1 and the command contains `keystroke`

### Requirement: HTTPServer fixture must wire engine as instance attribute
The `TestHTTPAPIWithEngine.test_server` fixture SHALL set `server.engine = engine` on the `HTTPServer` instance, not on the `RequestHandler` class.

#### Scenario: GET /status accesses engine via server attribute
- **WHEN** a request is made to `GET /status` on the test server
- **THEN** `self.server.engine` resolves correctly and returns engine status

#### Scenario: POST /start accesses engine via server attribute
- **WHEN** a request is made to `POST /start` on the test server
- **THEN** `self.server.engine` resolves correctly and triggers recording

### Requirement: AudioEngine start must not hang with mocked Popen
Tests that call `AudioEngine.start()` or `Engine.start_recording()` with `subprocess.Popen` mocked SHALL configure the mock so `poll()` returns `None` during the readiness polling phase.

#### Scenario: Mocked Popen poll returns None during readiness
- **WHEN** `AudioEngine.start()` is called with `Popen` mocked and `poll.return_value = None`
- **THEN** `_wait_for_recording_ready()` exits when the output file exceeds `_MIN_RECORDING_SIZE`

#### Scenario: Full workflow with mocked audio completes
- **WHEN** `Engine.start_recording()` → `Engine.stop_recording()` → `Engine.run_transcription()` is called with proper Popen mocking
- **THEN** the workflow completes without hanging and returns transcribed text

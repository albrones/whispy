## MODIFIED Requirements

### Requirement: HTTP API Interface

The API interface SHALL provide a set of RESTful endpoints to allow external control and status
monitoring of the daemon. The asynchronous stop endpoint (`/stop-async`) SHALL signal the
transcription worker via the engine's public stop event so that transcription proceeds in the
background, and SHALL return a success response rather than an error. The synchronous stop endpoint
(`/stop`) SHALL stop recording and then wait for the same background transcription worker to finish
handling it — including, in streaming mode, draining the chunk queue and assembling the recognized
chunk text — before responding, rather than transcribing ad hoc on the HTTP request thread. `/stop`
SHALL NOT mutate engine/FSM state directly; it SHALL delegate to the engine so there is exactly one
code path (used by both the hardware trigger-release flow and the HTTP API) that decides when a
recording/transcription cycle is complete. A `/stop` call made while nothing is recording SHALL be a
no-op that returns no text, without side effects.

#### Scenario: Status Check

- **WHEN** a GET request is made to `/status`
- **THEN** the API SHALL return a JSON object containing current recording, transcription, and
  listener status

_Tier: unit-mocked — `test_api/test_server.py` (real HTTP server, engine with mocked audio/Whisper)._

#### Scenario: Manual Start/Stop

- **WHEN** a POST request is made to `/start` or `/stop`
- **THEN** the API SHALL trigger the corresponding command in the core engine and return a status
  response

_Tier: unit-mocked — `test_api/test_server.py`._

#### Scenario: Async stop signals the worker

- **WHEN** a POST request is made to `/stop-async`
- **THEN** the API SHALL stop recording, set the engine's stop event so the transcription worker
  wakes, and return a 200 response with `{"status": "stopping"}` (without raising)

_Tier: unit-mocked — `test_api/test_server.py`._

#### Scenario: Sync stop returns assembled streaming text

- **WHEN** a POST request is made to `/stop` while streaming is enabled and one or more chunks were
  recognized during the recording
- **THEN** the API SHALL respond `200` with `{"status": "done", "text": <assembled chunk text>}`,
  reflecting the same text the transcription worker injected — not an empty/`null` result

_Tier: unit-mocked — `test_api/test_server.py` (regression test; chunk worker driven with a mocked
transcribe call, asserts `/stop`'s JSON `text` matches the assembled chunks)._

#### Scenario: Sync stop is a no-op when nothing was recording

- **WHEN** a POST request is made to `/stop` while the engine is not recording
- **THEN** the API SHALL respond `200` with `{"status": "done", "text": null}` and SHALL NOT mutate
  FSM state, start a transcription, or play the success cue

_Tier: unit-mocked — `test_api/test_server.py`._

#### Scenario: Sync stop does not double-fire the success cue

- **WHEN** a POST request to `/stop` completes a recording that produced real transcribed text
- **THEN** the success notification cue SHALL play exactly once (fired by the transcription worker),
  not once more by the HTTP handler

_Tier: unit-mocked — `test_api/test_server.py` (notifier call count asserted)._

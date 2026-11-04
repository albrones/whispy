## Purpose

Lets scripts, tests and, later, a Linux compositor key binding drive Whispy V2
locally, and guarantees that only one V2 runs per user.

## ADDED Requirements

### Requirement: V2 listens on an owner-only local socket
While running, V2 SHALL listen on a Unix domain socket at `~/.whispy/v2/control.sock`, overridable by `WHISPY_V2_SOCKET`. The socket's directory SHALL have mode 0700 and the socket SHALL have mode 0600. V2 SHALL open no network port.

#### Scenario: Directory and socket are private
- **WHEN** V2 starts with no `~/.whispy/v2/`
- **THEN** the directory SHALL be created with mode 0700 and the socket SHALL have mode 0600

_Tier: unit — `control` module on a temporary directory._

#### Scenario: No TCP listener
- **WHEN** V2 is running
- **THEN** `lsof -iTCP -sTCP:LISTEN` SHALL list no port owned by the V2 process

_Tier: script._

### Requirement: The socket speaks a line protocol
Each request SHALL be one line: `start`, `stop`, `toggle` or `status`. Each SHALL get one reply line. `start` SHALL act as a trigger press held down, and `stop` as its release, held long enough to count as a hold. `toggle` SHALL act as a short tap. `status` SHALL reply with a one-line JSON object naming the state, whether models are loaded, whether V2 is yielding to V1, and the last problem. An unknown request SHALL get an `error` reply and change nothing.

#### Scenario: start then stop dictates
- **WHEN** a client sends `start`, waits 2 s, then sends `stop`
- **THEN** V2 SHALL record for those 2 s, transcribe and deliver the text exactly as for a held Fn

_Tier: unit — controller with a fake capture and inserter._

#### Scenario: status while idle
- **WHEN** a client sends `status` while V2 is idle with models loaded
- **THEN** the reply SHALL be JSON with `"state":"idle"` and `"models_loaded":true`

_Tier: unit._

#### Scenario: Unknown request
- **WHEN** a client sends `record`
- **THEN** the reply SHALL start with `error` and the state SHALL be unchanged

_Tier: unit._

### Requirement: Socket requests and the Fn key share one state machine
Socket requests SHALL feed the same state machine as the Fn key, with the same rules. A `start` while recording, or a `stop` while idle, SHALL be ignored like an unmatched key edge. While V2 yields to V1, `start` and `toggle` SHALL be refused with a reply that says V1 holds the trigger.

#### Scenario: Yielding to V1
- **WHEN** V1 is running and a client sends `start`
- **THEN** V2 SHALL NOT record and the reply SHALL say that V1 is running

_Tier: unit — `machine`._

### Requirement: Only one V2 runs per user
On startup, V2 SHALL connect to the socket path first. If a V2 answers there, the new process SHALL exit without touching the socket. If nothing answers, V2 SHALL remove the stale socket file and listen. On exit, V2 SHALL remove its socket.

#### Scenario: A second launch exits
- **WHEN** V2 is running and a second V2 process starts
- **THEN** the second process SHALL exit within 2 s and the first SHALL keep answering `status`

_Tier: unit — two listeners on a temporary path._

#### Scenario: A stale socket left by a crash
- **WHEN** the socket file exists but no process listens on it
- **THEN** V2 SHALL replace it and start normally

_Tier: unit._

## MODIFIED Requirements

### Requirement: Event tap recovers from OS disablement and callback errors
The macOS event tap SHALL re-arm itself when the OS disables it, and SHALL contain exceptions raised by trigger callbacks, so the hotkey keeps working for the whole session.

Recovery SHALL NOT depend on the listener receiving the disablement event. The
disablement notification is delivered through the very tap whose health is in
question, and it is delivered once; a recovery path reachable only through that
channel leaves the trigger key permanently dead whenever the notification is
missed or the re-enable does not take. The listener SHALL therefore also verify
tap liveness on a bounded recurring interval and re-enable a tap it finds
disabled, independently of any event arriving.

Both recovery paths SHALL be retained. The event-driven path recovers faster and
carries the disablement *reason*, which the liveness check cannot observe and
which is the evidence needed to attribute recurring disablements to a cause.

Every recovery SHALL be recorded in the daemon log (`~/.whispy.log`) at WARNING
level, so that a re-arm is correlatable against the `[fsm]` and `[audio]` lines
around it and so that recurrence is countable rather than invisible. A recovery
SHALL NOT be reported only to a stream that is discarded when Whispy runs as a
GUI `.app`.

#### Scenario: OS disables the tap
- **WHEN** the tap receives `kCGEventTapDisabledByTimeout` or `kCGEventTapDisabledByUserInput`
- **THEN** it SHALL re-enable the tap, continue delivering events, and record the recovery and its reason in the daemon log at WARNING

_Tier: unit-mocked — `test_event_tap_e2e.py` (Quartz mocked)._

#### Scenario: The tap is disabled without a disablement event reaching the listener
- **WHEN** the tap is disabled and no `kCGEventTapDisabledByTimeout` / `kCGEventTapDisabledByUserInput` event is delivered to the callback
- **THEN** the periodic liveness check SHALL observe the disabled tap within its interval, re-enable it, and record the recovery in the daemon log at WARNING

_Tier: unit-mocked — `test_event_tap_e2e.py` (liveness probe driven directly, Quartz mocked)._

#### Scenario: A healthy tap is not repeatedly re-enabled
- **WHEN** the liveness check runs against a tap that is enabled
- **THEN** it SHALL NOT re-enable the tap and SHALL NOT emit a recovery log line

_Tier: unit-mocked — `test_event_tap_e2e.py`._

#### Scenario: The trigger key still works after a disablement during live typing
- **WHEN** a toggle-mode dictation with live typing enabled runs long enough for the OS to disable the tap
- **THEN** the trigger key SHALL still stop the recording afterwards without restarting the app, and `~/.whispy.log` SHALL contain the recovery line

_Tier: macos-real — requires a real event tap and real synthetic keystroke injection._

#### Scenario: A trigger callback raises
- **WHEN** a trigger press/release callback raises an exception
- **THEN** the tap SHALL log and continue, and SHALL NOT let the exception disable the tap or kill the listener thread

_Tier: unit-mocked — `test_event_tap_e2e.py`._

## ADDED Requirements

### Requirement: A tap recovery during a toggle-mode recording is reported, not guessed at
When the tap is re-armed while the dictation state machine is in RECORDING and
the active trigger mode is `toggle`, the system SHALL report that a stop-press
may have been lost during the outage, in the daemon log at WARNING.

The system SHALL NOT synthesize a press to resolve this condition. In toggle
mode a press means *stop the recording*, and whether one occurred while the tap
was disabled is an edge that cannot be reconstructed from state after the fact.
A synthesized press would end a dictation the user is still speaking into,
turning a recoverable annoyance into lost speech.

This is deliberately asymmetric with the existing missed-**release** recovery,
which remains unchanged: a release is verifiable against the live modifier flag
state, and a spurious one only ends a recording the user had already ended.

#### Scenario: Re-arm during a toggle-mode recording
- **WHEN** the tap is re-enabled (by either recovery path) while the state machine is in RECORDING and the trigger mode is `toggle`
- **THEN** the system SHALL record at WARNING that a stop-press may have been lost, and SHALL leave the state machine in RECORDING

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Re-arm while idle is not reported as a lost press
- **WHEN** the tap is re-enabled while the state machine is in IDLE
- **THEN** the system SHALL record the recovery itself but SHALL NOT report a possibly-lost stop-press

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Hold-mode release recovery is unchanged
- **WHEN** the tap is re-enabled while the trigger mode is `hold` and the trigger modifier is no longer physically held
- **THEN** the existing missed-release recovery SHALL still emit the release and stop the recording, exactly as before this change

_Tier: unit-mocked — `test_event_tap_e2e.py`._

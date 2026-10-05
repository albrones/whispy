## Why

Whispy strands in `RECORDING` and the only remedy is a restart. The user hit it twice in one session; the daemon log shows it is not rare and not new.

Measured in `~/.whispy.log` (single machine, toggle mode, Right Option trigger):

| Signal | Count |
|---|---|
| `[audio] capture open` (recordings since `e56bc76`) | 33 |
| `[audio] capture closed` | 31 |
| **Recordings that never stopped** | **2** |
| `[engine] watchdog: RECORDING hit the 300s limit` (earlier, same signature) | 3 |

Log line 781 is the proof of shape: 300 seconds of consecutive `Recording is near-silent — discarding` before the watchdog cut it. The user had stopped speaking minutes earlier. Audio capture was alive; the trigger was dead.

Both unrecovered strands share one shape — the stopping press never reaches the engine:

```
IDLE -> RECORDING
capture open
chunk -> "..."   [inject ok]      <- live typing fired
chunk -> "..."   [inject ok]
<nothing>                          <- stopping press swallowed
<user restarts the app>
```

No `capture closed`. No `RECORDING -> TRANSCRIBING`. The stop path was never entered.

The `fix-fsm-hang-recovery` change already shipped three mitigations for this failure class. **All three miss this configuration** (`trigger_mode: "toggle"`, modifier trigger, `type_while_speaking: true`, `copy_to_clipboard: false`):

1. **Tap re-arm is event-driven only.** `event_tap.py` re-enables the tap when it receives `kCGEventTapDisabledByTimeout` / `ByUserInput`. That works — but nothing ever *checks* whether the tap is live, so any path where the disablement notification is missed or the re-enable does not take leaves the hotkey permanently dead with no retry.
2. **Missed-event recovery is hold-mode-only.** `_resync_after_rearm` synthesizes a missed **release**. In toggle mode a release is a deliberate no-op (`_handle_trigger_release_signal`): only the **press** carries meaning. The recovery mechanism does nothing for a toggle user.
3. **The diagnostics that would prove or disprove any of this are discarded.** `whispy_daemon.py` routes stderr to a bare `StreamHandler`, which under a GUI `.app` launch goes nowhere — `~/.whispy-error.log` does not exist on this machine despite being documented in `CLAUDE.md` and the user-facing docs. Every tap diagnostic (`tap was disabled by the OS — re-armed`, `recovered a trigger release missed during tap outage`, `trigger callback raised`) is a `print(file=sys.stderr)` into the void.

Gap 3 is why this shipped unnoticed and why the diagnosis above is inference from silence rather than from evidence. It is fixed first.

The aggravating factor is `type_while_speaking`: live typing runs `osascript` → System Events `keystroke` **during** `RECORDING`, and those synthetic events flow back through Whispy's own `kCGSessionEventTap`. Hundreds of synthetic key events per chunk is precisely the input burst `kCGEventTapDisabledByUserInput` exists to signal. The feature did not create the bug; it turned a latent one into roughly a 6%-per-recording one.

## What Changes

- **Capture stderr to a file.** `whispy_daemon.py` gains a rotating file handler for `~/.whispy-error.log`, restoring the file `CLAUDE.md` and the docs already promise. Every existing `print(..., file=sys.stderr)` diagnostic becomes readable without changing a single call site.
- **Make the event tap self-healing rather than notification-dependent.** The listener's run loop already wakes every 500 ms (`CFRunLoopRunInMode(..., 0.5, False)`). On each pass it checks `CGEventTapIsEnabled` and re-enables a disabled tap. The tap recovers within 500 ms of *any* disablement, whether or not the notification event was delivered, instead of depending on an event arriving through a channel that is itself down.
- **Log tap disablement and recovery at WARNING, in the daemon log.** Re-arms become countable rather than invisible, so the next occurrence is evidence instead of a report. This is what makes the causal claim above falsifiable.
- **Surface an unrecoverable toggle-mode press loss instead of synthesizing one.** When the tap is re-armed while the FSM is in `RECORDING` under toggle mode, the engine SHALL log the condition. It SHALL NOT synthesize a press: a press means *stop the recording*, so fabricating one on a guess would end a live dictation the user did not end. Detection and disclosure only.

Non-goals, deliberately:

- **Not** lowering `RECORDING_MAX_S`. Its 300 s bound serves "the user forgot to stop a toggle dictation", and its graceful clipboard delivery is correct for that. Overloading it with "the hotkey is dead" would make both worse. With a self-healing tap the strand should not reach it.
- **Not** flipping `copy_to_clipboard`. The pending `fix-dictation-text-fidelity` change already proposes that default flip for unrelated reasons (keyboard-layout corruption), and it would independently collapse the synthetic-event flood from hundreds of keystrokes per chunk to one Cmd+V. The two changes reinforce each other; duplicating the decision here would create a conflict. Noted as a cross-reference, not adopted.
- **Not** filtering Whispy's own synthetic events out of its tap. A source-based filter is the theoretically tidier fix, but it is strictly larger than the liveness check and only addresses the self-inflicted share of disablements. The liveness check is correct for every cause.

## Capabilities

### New Capabilities

_None — this hardens existing behaviors._

### Modified Capabilities

- `event-listener`: the existing "Event tap recovers from OS disablement and callback errors" requirement is strengthened. Recovery SHALL NOT depend on receiving the disablement event: the listener SHALL verify tap liveness periodically and re-enable a disabled tap. Recovery events SHALL be logged to the daemon log at WARNING. A tap re-arm occurring while a toggle-mode recording is in progress SHALL be reported and SHALL NOT be resolved by synthesizing a press.
- `core-engine`: the daemon-logging requirement is extended — stderr diagnostics SHALL be captured to a rotating `~/.whispy-error.log`, not written to a stream that is discarded under a GUI `.app` launch.

## Impact

- `whispy_daemon.py` — logging configuration: add the `~/.whispy-error.log` rotating handler.
- `src/whispy/hardware/event_tap.py` — the `_run` run-loop body gains the `CGEventTapIsEnabled` liveness check; diagnostics move from `print(file=sys.stderr)` to `logger.warning`.
- `src/whispy/core/engine.py` — report a tap re-arm that lands mid-recording in toggle mode.
- `docs/` — the log-file reference already names `~/.whispy-error.log`; verify it now matches reality.
- Tests: `tests/test_event_tap.py` (liveness re-enable, disabled-tap recovery without a notification event), `tests/test_engine.py` (toggle-mode re-arm reporting). `CGEventTapIsEnabled` is confirmed available in the project's pinned `pyobjc-framework-Quartz`.
- No new dependency. No API change. No config change. No change to the happy path.
- `website/index.html` — no user-facing feature change; no update required.

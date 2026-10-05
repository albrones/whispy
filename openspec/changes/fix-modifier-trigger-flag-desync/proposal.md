## Why

Whispy strands in `RECORDING` with the pill on screen and the trigger dead; the only remedy is a restart. `fix-toggle-trigger-strand` shipped a fix for this symptom — a `CGEventTapIsEnabled` liveness probe on the listener's run loop — and the strand happened again on 2026-09-29 with that fix installed and running.

The installed bundle was verified to carry the probe (`/Applications/Whispy.app/Contents/Resources/lib/python3.14/whispy/hardware/event_tap.py` contains `CGEventTapIsEnabled`, byte-identical to source). The daemon log is the disproof:

| Signal | Value |
|---|---|
| `[audio] capture open` | 171 |
| `[audio] capture closed` | 166 |
| **Recordings that never stopped** | **5** |
| `[engine] watchdog: RECORDING hit the 300s limit` | 3 |
| **`[event-tap]` lines of any kind** | **0** |

Zero `[event-tap]` lines means the OS never disabled the tap. Both re-arm paths log at WARNING to the daemon log, and neither fired. **The tap was healthy the whole time.** The liveness probe hardened a path that is not the one failing here, so this change addresses a different root cause and does not supersede that one.

The shape in the log, for the 2026-09-29 strand:

```
IDLE -> RECORDING
capture open
chunk 4.53s -> "Comme dans l'etterbox D."     [inject ok]
chunk 7.86s -> "J'aimerais pouvoir..."        [inject ok]
chunk 4.83s -> "voilà et que ce soit..."      [inject ok]
<nothing>                                      <- the stopping press is swallowed
Microphone access already granted.             <- the user restarts the app
```

No `capture closed`, no `RECORDING -> TRANSCRIBING`, no tap diagnostic. The stop path was never entered, and the listener was alive.

### The mechanism

The configuration is `trigger: 61` (Right Option), `trigger_mode: "toggle"`. A modifier trigger has no `key_up`: it arrives as `flags_changed`, and `decode_trigger_event` derives press from release by **diffing against the previous event's flags** (`event_decode.py`):

```
changed = flags ^ prev_flags
changed & flags  -> press
changed & prev   -> release
```

`event_tap.py` updates `self._prev_flags` only on `flags_changed` events, and **never resynchronises it from live modifier state** except inside `_resync_after_rearm`, which only runs on a tap re-arm — an event that this log shows never occurs. A single missed or misordered `flags_changed` therefore desynchronises the trigger permanently, with no recovery path and no diagnostic.

The desync is not hypothetical, because `MASK_OPTION` (`0x80000`, `kCGEventFlagMaskAlternate`) is **shared by Left and Right Option**. Left Option is pressed constantly on the French AZERTY layout this machine uses (`@ # { } [ ] | \`). Any overlap between a Left Option press and the Right Option stop-press leaves the shared bit already set, so the diff is zero and the stopping press decodes as `None`:

```
 prev   event                          keycode  decoded
 ----   ----------------------------   -------  ---------------------
 0      R-Opt down   opt 0->1            61     press   -> START
 OPT    R-Opt up     opt 1->0            61     release -> no-op (toggle)
 0      L-Opt down   opt 0->1            58     None (kc != 61); prev := OPT
 OPT    R-Opt down   opt stays 1         61     changed == 0 -> None
                                                ^^^ STOP PRESS SWALLOWED
```

`type_while_speaking` is an aggravating factor on the same mechanism rather than a separate one: live typing drives `osascript` → System Events, whose synthetic modifier events flow back through Whispy's own `kCGSessionEventTap` and write into `_prev_flags` like any other event.

## What Changes

- **Decode a modifier trigger from its own device-dependent flag bit instead of a diff.** macOS sets a distinct bit per physical side (`NX_DEVICERALTKEYMASK = 0x40` for Right Option, `0x20` for Left Option, and the matching pairs for Control, Shift and Command). For a modifier trigger the decoder SHALL test the bit belonging to the configured key: set means press, clear means release. The decision becomes a pure function of the current event alone.
- **Retire `prev_flags` from the modifier decode path.** With the device bit there is no accumulated state to desynchronise, so no missed event, no synthetic event and no same-mask key on the other side of the keyboard can strand the trigger. `prev_flags` stays in the signature for the Fn path and for callers that still pass it, and the diff becomes the documented fallback for a modifier with no known device bit.
- **Keep `_prev_flags` fresh from every event that carries flags.** `key_down` and `key_up` events also carry the live modifier state; tracking them costs nothing and bounds the staleness of the fallback path.
- **Log a swallowed trigger event once per recording.** When an event on the configured trigger keycode decodes to `None`, the listener SHALL log it at WARNING (rate-limited), so the next occurrence of this failure class is evidence rather than an inference from silence — the same gap `fix-toggle-trigger-strand` identified for tap outages, applied to decode.

Non-goals, deliberately:

- **Not** reverting or weakening the `CGEventTapIsEnabled` liveness probe from `fix-toggle-trigger-strand`. It covers a real, distinct failure mode that this log simply does not exhibit. Both are needed.
- **Not** synthesising a press when a desync is detected. A press means *stop the recording*; fabricating one on a guess would end a live dictation the user did not end. This change removes the desync rather than compensating for it.
- **Not** touching `RECORDING_MAX_S` or the FSM watchdog. They remain the backstop for causes neither change anticipates.
- **Not** fixing `_KEYCODE_TO_NAME[61] = "f3"` (keycode 61 is Right Option; `kVK_F3` is 99). The UI reads its label from the `config.py` preset table (`("Right Option", 61)`), so the wrong entry only affects one startup `print` in `event_tap.py`. Noted here so it is recorded, left out so this change stays the size of its own claim.

## Capabilities

### New Capabilities

_None — this corrects the behaviour of an existing decode path._

### Modified Capabilities

- `event-listener`: the "Modifier-key triggers emit a release" requirement is strengthened. Press/release for a modifier trigger with a known device-dependent bit SHALL be derived from that bit on the current event, not from a diff against previously observed flags, so the decode cannot desynchronise. The flag-diff path is retained only as the fallback for modifiers with no known device bit. An event on the configured trigger keycode that decodes to neither press nor release SHALL be reported.

## Impact

- `src/whispy/hardware/event_decode.py` — a device-bit table keyed by trigger keycode, consulted by `decode_trigger_event` before the existing flag-diff branch.
- `src/whispy/hardware/event_tap.py` — track flags from every event that carries them, not only `flags_changed`; report a trigger-keycode event that decodes to `None`.
- Tests: `tests/test_event_decode.py` — press/release from the device bit; the Left/Right Option interleaving above, which is the regression this change exists to prevent; a modifier with no device bit still decoding through the diff path. All pure, no Quartz, no device.
- The device-bit values are `IOLLEvent.h` constants, not exported by pyobjc; they are hardcoded exactly as `NX_SECONDARYFNMASK` already is in this module. **A one-shot live confirmation on this machine is the first task**, with the flag-diff fallback retained if a bit does not appear as documented.
- No new dependency. No config change. No API change. No change to the happy path, to hold mode, or to the Fn default trigger.
- `website/index.html` — no user-facing feature change; no update required.

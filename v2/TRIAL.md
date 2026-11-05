# Whispy V2 trial

V2 replaces V1 only if it survives everyday dictation with V1 quit. This page
fixes, **before the trial starts**, how it runs and what it must show. Each
criterion is a number printed by a command, so the verdict cannot drift
toward an impression.

## Setup (once, on the Mac)

1. Quit V1 from its menu bar icon. In its Settings menu, uncheck **Start at
   login** so it does not come back at the next login.
2. From the repository root: `make v2-reinstall`. This installs
   `/Applications/Whispy V2.app` next to V1 without touching V1.
3. Grant the three permissions to **Whispy V2**, not to a terminal, in System
   Settings → Privacy & Security: Microphone (asked at the first dictation),
   Input Monitoring, Accessibility.
4. Set Keyboard → « Press 🌐 key to » → **Do Nothing**.
5. In V2's menu, check **Start at login**.
6. Write down the trial start date. Then record the reference point on your
   labelled clips:
   ```bash
   cd v2 && cargo run --release --bin banc -- --labelled
   ```

## Length

At least **3 days with dictation** and **50 dictations**, both read from
`banc --trial`. Five days is better. Stop early only for a criterion that
already fails beyond doubt, such as a stuck app.

## During the trial

Dictate as you would with V1. When something V1 did is missed, add one line
to the notes (see Result). Do not fix V2 during the trial: a change resets
the clock.

## Exit criteria

V2 passes only if **all five** hold:

| # | criterion | read from | pass |
|---|---|---|---|
| 1 | lost speech | `banc --trial --since <start>`: « lost share », V2 beside V1 | V2's share ≤ V1's |
| 2 | latency | `banc --trial --since <start>`: release-to-delivery p95 over inserted dictations | ≤ 1.5 s |
| 3 | accuracy on your voice | `banc --labelled`: WER against V1's baseline | ≤ V1 + 1 point |
| 4 | no invented text | `banc --labelled`: text on noise clips | 0 |
| 5 | never stuck | `banc --trial`: `clipboard` outcomes, plus the V2 log's unexplained restarts (see below) | 0 |

For criterion 5:
- the 5-minute watchdog is the only path that delivers to the clipboard
  instead of pasting, so each `clipboard` outcome is a recording V2 did not
  stop when asked;
- count the `whispy2 started` lines in the log (`grep -h 'whispy2 started'
  ~/.whispy/v2/whispy2.log* | wc -l`), then subtract the logins and the
  `make v2-reinstall` runs of the trial.

Anything left over is a time V2 had to be relaunched to rescue it.

**Known blind spot:** V2 counts a dictation as lost only when the whole
dictation came back empty. In a long dictation, one silent 20 s piece is not
flagged, while V1 counts each streamed chunk. The shares are weighted by
duration to limit the gap, but V2's share can only be lower than or equal to
the truth. Listen to `~/.whispy/v2-lost/` (also listed by `banc --trial`) if
criterion 1 is close.

## Result

Record the verdict when the trial ends: go or no-go, the five numbers, and
the list of V1 features you missed. Put it in the proposal of the next change,
`openspec/changes/v2-parity/`. That change ports only what the trial showed
was missing, then switches V1 off for good.

**Rollback at any time:** quit Whispy V2, uncheck its Start at login, and
open `/Applications/Whispy.app`.

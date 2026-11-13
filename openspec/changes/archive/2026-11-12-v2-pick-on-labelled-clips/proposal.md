## Why

The full bench must name the configuration the core uses by default (criterion
7 of the V2 card) and exits 2 when it does not. Rerun on 2026-11-12 it picked
`parakeet / louder` against the default `parakeet then whisper / padded`: the
pick was ranked on how many clips of `~/.whispy/lost/` came back with text.
Those clips carry no label (the user's own listening found 13 of 20 to be
noise, so text there may be invented) and V1 rotates the folder: the 20 clips
of 2026-10-25 were gone, and one clip out of 20 new ones moved the pick.

The card already settled criterion 3 on the user's labelled clips
(`~/.whispy/bench`). The pick must rest on the same evidence.

## What Changes

- The full bench replays the labelled clips through every configuration and
  builds, per configuration, the criterion 3 verdict of `banc --labelled`
  against V1's `baseline.json`. Each configuration runs as a whole `Pipeline`:
  the labelled clips are real dictations, and one engine call on a whole clip
  (how the other groups are measured) skips the split and join the app does;
  measured that way the same default scored 206 word errors instead of 95.
- The pick rule: text on non-speech **or on a clip labelled noise** rules a
  configuration out; then V1's reference WER guard; then, on the labelled
  clips, criterion 3 holds, the most lost speech back, the fewest word errors;
  then the oracle's lost speech clips; the unlabelled lost clips rank only
  when there are no labelled clips; then reference and quiet WER, ~5 s p95.
- In the bench, as in the pipeline, an answer without a letter or a digit
  ("...") counts as empty, so a fallback pair is scored as the app behaves.
- `bench/REPORT.md` gains a per-configuration table of the labelled clips
  (counts only) and the criterion 3 line of the pick.

## Capabilities

### Modified Capabilities
- `v2-transcription-core`: the bench ranks the pick on the user's labelled clips.

## Impact

- Code: `v2/banc/src/{labelled,measure,report,main}.rs`, `v2/README.md`,
  `v2/bench/REPORT.md`.
- No runtime change to the library or the app: the default stays
  `parakeet then whisper / padded`.

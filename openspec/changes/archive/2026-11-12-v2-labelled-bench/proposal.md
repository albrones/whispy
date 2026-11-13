## Why

Criterion 3 of the V2 card (does V2 stop losing speech V1 lost, without being
worse than V1 on words) was judged against a large-model oracle and an ear
check that never finished. Meanwhile the user labelled their own clips
(`~/.whispy/bench`: references, kinds, V1's baseline). The bench must settle
criterion 3 on those labels.

## What Changes

- `banc --labelled [dir]` replays the labelled clips (default `~/.whispy/bench`)
  through the default V2 pipeline (Parakeet, then whisper loaded on demand) and
  prints, against V1's `baseline.json`: (a) the share of lost "chunk" clips that
  come back with text, (b) the noise clips that got invented text, (c) the word
  error rate over chunk and dictation clips, with V1's text normalization.
- Nothing from the clips (audio, references, texts) is committed or written;
  texts are printed only with `WHISPY_BANC_SHOW_LOST_TEXT=1`.
- The rest of the bench is unchanged.

## Capabilities

### Modified Capabilities
- `v2-transcription-core`: the bench can score V2 on user-labelled clips.

## Impact

- Code: `v2/banc/src/labelled.rs`, `v2/banc/src/main.rs`, `v2/README.md`.
- No runtime change to the library or the app.

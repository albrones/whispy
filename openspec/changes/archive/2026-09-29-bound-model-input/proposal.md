## Why

On 2026-09-29 the Mac panicked (`userspace watchdog timeout: no successful
checkins from WindowServer`). The panic report showed one Python process at
25.3 GB resident, with the compressor at 100 % of its segment limit and swap
full: an ad-hoc benchmark had fed a 180 s clip to Parakeet in a single call
under the CoreML provider.

Live dictation cannot do that: streaming cuts chunks at 8 s, and at 12 s
unconditionally. But two paths still hand the model a whole file of any
length (up to `RECORDING_MAX_S` = 300 s):

- `run_transcription`, used when `streaming_enabled` is false;
- `transcribe_file`, behind `POST /transcribe-file`.

Measured on M1 Pro, int8 model, pinned CPU provider, one call per clip:

| clip | peak RSS | decode |
| ---: | ---: | ---: |
| 8 s | 1268 MB | 0.25 s |
| 30 s | 1476 MB | 0.87 s |
| 60 s | 1688 MB | 1.91 s |
| 180 s | 3503 MB | 8.19 s |
| 300 s | 3688 MB | 17.81 s |

CPU does not crash the machine, but memory grows with clip length, and nothing
bounds it if the provider pin ever changes: CoreML turned the same 180 s into
25 GB.

**Need, in one sentence:** no single model call may receive an unbounded clip,
whatever path the audio took.

## What Changes

- `AudioEngine.transcribe` splits any clip longer than `MODEL_INPUT_MAX_S`
  (30 s) into pieces before the model sees it, and transcribes each piece
  through the same gates and trim.
- Pieces are cut where the live segmenter would cut (pauses, then its own
  ceiling); a piece still over the bound — a long silence before the first
  word — is sliced at fixed offsets. No audio is dropped.
- Piece texts are joined with a single space.

Measured after the change, same 180 s clip through `transcribe`: 14 calls,
longest 13.5 s, peak RSS 1600 MB (was 3503 MB), 7.8 s total.

## Raison d'être

- **Usage:** every dictation with streaming off, and every validation run over
  `/transcribe-file`; the guard is also what keeps a future provider change from
  taking the machine down again.
- **Without it:** a long whole-file transcription holds several GB and the
  decode blocks for up to 18 s; under CoreML, the machine panics.

## Refusé

- **A memory watchdog that kills the model call** — reacts after the damage,
  and loses the dictation.
- **Refusing long files** — loses the user's speech; splitting keeps it.
- **Boundary-aware punctuation join (streaming's `join_chunk`)** — not on
  `main` yet; a plain space join is enough for a path that is off by default.

## Coût

- No dependency, no network call, no served weight (desktop app).

## Impact

- `src/whispy/core/audio.py`, `src/whispy/core/segmentation.py`.
- Spec `asr-backend`: one requirement added.

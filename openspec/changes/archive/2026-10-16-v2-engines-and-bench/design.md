# Design — V2 engines and bench

## Shape

```
v2/                      Cargo workspace
├── whispy-core/         library the app will link
│   ├── audio            WAV I/O, peak RMS, loudness, padding
│   ├── vad              WebRTC VAD span (aggressiveness 2, 30 ms) and trim
│   ├── split            pieces of at most 20 s, cut in the longest pause
│   ├── mel              NeMo 128-bin log-mel (port of onnx-asr's NumPy preprocessor)
│   ├── parakeet         TDT greedy decoding on ONNX Runtime, CPU provider
│   ├── whisper          whisper.cpp small, language detected
│   ├── models           finds the files already on the Mac, never downloads
│   └── pipeline         Pipeline { primary, fallback, strategy }, the defaults
└── banc/                the bench binary
```

The app (next PR) only needs `Pipeline::load_default()` and
`Pipeline::transcribe(&[f32]) -> Transcript`. Engines sit behind the
`Transcriber` trait, which is also the seam for the pipeline's unit tests.

## Decisions

### Parakeet is ported, not wrapped

`transcribe-rs` already runs Parakeet on `ort`, but its decoder ignores the
TDT duration head (it advances one frame per blank, as RNN-T would), so it
would not decode like V1, and it needs a `nemo128.onnx` preprocessor the V1
cache does not hold. The port is ~200 lines: onnx-asr's `NemoConformerTdt`
greedy loop and its NumPy NeMo preprocessor, reading the very files V1
downloaded. A unit test pins the computed Slaney filterbank to the values of
onnx-asr's shipped `fbanks.npz`, and the features match V1's within 2·10⁻⁵.
On the 50 reference and quiet speech clips the port returns V1's exact text 48
times (one punctuation difference, one borderline word: « GitHub » read « JEB »
by V1 and « J-Eub » by V2). Switching ONNX Runtime 1.22 → 1.24 or toggling
prepacking did not move that word.

### Whisper's doubt is a filter

With temperature fallback on, whisper resampled noise into a different
garbage on every run (Georgian, Khmer, Hangul, English fragments) and "got
text" for 13 of the 20 lost clips. Temperature fallback is off, and a segment
is dropped when its no-speech probability is above 0.6, its mean token log
probability below −1, or it holds a non-Latin letter. Measured on the lost
clips: the real dictations sit at no-speech 0.07–0.09, log probability −0.41
to −0.80; the fillers and noise at 0.91 or −3.6 to −7.8.

### The pair does not fit in 1.5 GB

Parakeet alone peaks at 1090 MB for a 180 s dictation, whisper alone at
741 MB, both loaded at 1721 MB. Loading whisper only on a fallback and
dropping it afterwards would keep the steady state at ~1.1 GB but not the
peak. Left to the user: accept ~1.7 GB, or drop the fallback and lose the
recovered dictations.

### ONNX Runtime memory

Defaults put Parakeet alone at 1.67 GB peak RSS for a 180 s dictation in 20 s
pieces. Turning off memory patterns and weight prepacking, and allocating
initializers outside the arena, brings it to about 1.09 GB with the same text
and similar speed. Smaller pieces barely move it (10 s: −65 MB): the weights
dominate, not the activations.

### whisper.cpp on Metal

CPU whisper small spends ~1.2 s per clip whatever its length (it always
encodes a 30 s window). The `metal` feature brings that to ~0.5 s. This is
whisper.cpp's own Metal backend, not CoreML; Parakeet stays CPU-only. Memory
is measured as the physical footprint as well as RSS, so GPU buffers are
counted.

### Strategies are a ladder, measured one rung at a time

`raw` → `gated` (V1 gates + trim) → `louder` (quiet clips to RMS 0.05) →
`padded` (short clips get 0.5 s of silence each side), each alone and with the
other engine as fallback. A "context" complement (prepending carrier speech
and cutting its words out by timestamp) was left out: it needs a carrier voice
unlike the user's and a token-timestamp cut that can eat the first word.

### The bench derives fallbacks instead of rerunning them

Preparation is deterministic, so a fallback configuration's outcome is the
primary's text when non-empty, else the secondary's on the same input, and its
time is the sum. Each (engine, strategy, clip) runs once (five times for the
~5 s sentences), which keeps a full run to a few minutes.

### V1 is replayed, not re-implemented

`bench/v1_replay.py` imports V1's `AudioEngine.transcribe` from `src/` and
runs it with V1's venv, offline, with a private TMPDIR, and with the lost-clip
keeper disabled — so replaying never rotates `~/.whispy/lost/` or deletes the
running daemon's temp files.

## Risks

- The reference set is synthetic speech; it measures regressions, not the
  user's voice. The lost clips are the real voice, but have no known text.
- A lost clip may be noise: "text on 70 % of lost clips" can reward an engine
  that invents. The bench guards with a non-speech group (any text there
  disqualifies a configuration) and prints every lost clip's text for review.

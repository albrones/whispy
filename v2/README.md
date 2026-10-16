# Whispy V2 (Rust)

A rewrite of Whispy's core in Rust, compared against V1 on a bench before it
replaces anything. V1 (the Python app at the repository root) stays installed
and untouched.

This directory holds the first half: the transcription engines, the audio
pipeline and the bench. The macOS app (menu bar, Fn key, text insertion) comes
next and builds on the library below.

```
v2/
├── whispy-core/   library: engines, gates, splitting, PCM → text pipeline
├── banc/          the bench binary
└── bench/
    ├── reference/ synthetic reference clips with a known text (+ generate.sh)
    ├── v1_replay.py   runs V1's own engine on the same clips (read-only)
    └── REPORT.md  the last bench run: numbers and the default engine
```

## Build, test, bench

```bash
cd v2
cargo test --release
cargo clippy --release --all-targets -- -D warnings
WHISPY_V1_PYTHON=../.venv/bin/python cargo run --release --bin banc
```

The first build downloads ONNX Runtime's prebuilt library (the `ort` crate)
and compiles whisper.cpp (needs `cmake`). At run time nothing leaves the Mac:
the models are the files already downloaded, and the V1 replay runs with
`HF_HUB_OFFLINE=1`.

| model | where V2 looks | override |
|---|---|---|
| Parakeet TDT 0.6b v3, int8 ONNX | the Hugging Face cache V1 filled (`~/.cache/huggingface/hub/models--istupakov--parakeet-tdt-0.6b-v3-onnx`) | `WHISPY_PARAKEET_DIR` |
| whisper small (`ggml-small.bin`) | `~/.whispy/models/`, then `~/.jarvis/models/` | `WHISPY_WHISPER_MODEL` |

A missing model is an error naming the paths looked at; V2 never downloads one.

## The interface the app uses

```rust
use whispy_core::{Pipeline, Transcriber, Strategy, EngineKind};

// The configuration the bench picked (DEFAULT_ENGINE, DEFAULT_FALLBACK, DEFAULT_STRATEGY).
let mut pipeline = Pipeline::load_default()?;

// 16 kHz mono f32 samples in -1.0..1.0, the whole dictation (Fn pressed → released).
let transcript = pipeline.transcribe(&samples)?;
transcript.text;   // text to insert; empty when there was nothing to transcribe
transcript.engine; // Some("parakeet") / Some("whisper"), None when empty
```

- `Transcriber` is the engine trait (`name`, `transcribe(&[f32]) -> String`);
  `Parakeet` and `Whisper` implement it, and a test double can too.
- `Pipeline::new(primary, fallback, strategy)` builds any other configuration.
- `Pipeline::transcribe` splits a long dictation into pieces of at most
  20 s, cut in pauses (`split::pieces`), so memory stays bounded whatever the
  length; each piece goes through the strategy, the primary engine, then the
  fallback engine when the primary returns nothing.
- Loading takes about a second per engine: load once at startup, on a worker
  thread, and keep the pipeline. `Pipeline` is `Send`, not `Sync`: one
  dictation at a time.
- `audio::read_wav` reads the 16 kHz mono 16-bit WAVs V1 records and keeps.

### Strategies

| strategy | what the engine receives |
|---|---|
| `Raw` | the clip as captured |
| `Gated` | nothing for near-silence (peak RMS < 0.005) or too little voice (< 0.20 s voiced, WebRTC VAD); otherwise the clip cut to its voiced span ± 0.3 s |
| `Louder` | `Gated`, and a clip quieter than RMS 0.05 scaled up to it |
| `Padded` | `Louder`, and a clip under 3 s with 0.5 s of silence on each side |

The thresholds are V1's, measured on real dictation (see the comments in
`whispy-core/src/audio.rs` and `vad.rs`).

## What V1 taught, kept here

- **CPU provider only for Parakeet.** Under CoreML a 180 s clip reached 25 GB
  and took the Mac down.
- **One model call never gets an unbounded clip.** V1 measured 3.5 GB for 180 s
  in one call.
- **Silence and noise never reach an engine** once gated: Parakeet invents
  "Yeah." and "Thank you." on them, Whisper "Sous-titres réalisés par la
  communauté d'Amara.org".
- **Silence around a lone word makes Parakeet return nothing**: the clip is cut
  to its voiced span.
- **Quiet dictation is the real loss**: V1's lost clips that held speech sat at
  RMS 0.010–0.013 and came back at 0.05.
- **Language is detected, never forced**: forcing one made Whisper translate.

## Bench

`cargo run --release --bin banc` replays:

- the clips V1 lost (`~/.whispy/lost/`, or `WHISPY_LOST_DIR`);
- reference clips with a known text: **synthetic voices** generated with macOS
  `say` (FR and EN, short, ~5 s and long), plus V1's two validation fixtures;
- the same references turned down to the level of real lost dictation;
- silence and noise, where any text is invented;

through both engines and every strategy, alone and with the other engine as
fallback, and runs V1 on the same clips through `bench/v1_replay.py` with V1's
venv (`WHISPY_V1_PYTHON`). It measures the memory of a 180 s dictation in a
fresh process, writes `bench/REPORT.md`, and exits with code 2 when its pick
differs from the library's default.

See [`bench/REPORT.md`](bench/REPORT.md) for the latest numbers and the pick.
Lost clips are real dictation: the report gives their word counts, never their
text, unless `WHISPY_BANC_SHOW_LOST_TEXT=1` is set for a local read (do not
commit that report). The work copies of the clips are deleted when the bench
ends.

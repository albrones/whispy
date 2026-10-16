## 1. Core library (`v2/whispy-core`)

- [x] 1.1 Cargo workspace `v2/` with `whispy-core` and `banc`
- [x] 1.2 Audio helpers and V1's gates: WAV I/O, peak RMS, loudness, padding; WebRTC VAD span and trim
- [x] 1.3 Splitting into pieces of at most 20 s, cut in pauses, lossless
- [x] 1.4 NeMo 128-bin log-mel port, filterbank pinned to onnx-asr's values
- [x] 1.5 Parakeet TDT engine on ONNX Runtime CPU, files from V1's cache; memory settings measured
- [x] 1.6 whisper small engine (whisper.cpp, Metal), language detected, doubt filter
- [x] 1.7 `Transcriber` trait, `Pipeline` with strategy and fallback, defaults
- [x] 1.8 Unit tests (gates, trim, split, mel, detokenize, pipeline with scripted engines)

## 2. Bench (`v2/banc`)

- [x] 2.1 Reference clips with known text (`say`, FR/EN, short to long) + V1 fixtures, generator script
- [x] 2.2 Lost, reference, quiet and non-speech groups; WER, text rate, latency p50/p95, ~5 s p95
- [x] 2.3 V1 replay through its own engine, offline, without touching `~/.whispy/lost/`
- [x] 2.4 180 s memory probe in a fresh process (peak RSS and physical footprint)
- [x] 2.5 `bench/REPORT.md` with the pick; exit 2 when the core's default differs

## 3. Delivery

- [x] 3.1 Bench run, default set to the pick, numbers in the proposal
- [x] 3.2 `v2/README.md` documents the interface for the app
- [x] 3.3 CI job `v2` (fmt, test, clippy on macOS)
- [x] 3.4 `cargo test` and `cargo clippy -D warnings` green locally

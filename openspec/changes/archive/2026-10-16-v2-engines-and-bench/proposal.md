## Why

V1 still loses speech: `~/.whispy.log` counted 207 « Lost speech » for 264
transcriptions, and short or quiet utterances come back empty — « à améliorer,
je pense » took three tries (Régie card whispy #2). Card whispy #1 restarts the
core in Rust (V2, in `v2/`) and lets a bench, not belief, decide whether it does
better. This change is its first half: engines, audio pipeline and bench. The
macOS app (menu bar, Fn, insertion) is the second half.

**Need, in one sentence:** a transcription core that turns a dictation's PCM
into text without losing short or quiet speech, compared with V1 on the same
clips before anything replaces V1.

## What Changes

- New Cargo workspace `v2/`: library `whispy-core` (engines, gates, splitting,
  PCM → text `Pipeline`) and binary `banc`.
- Two engines behind one `Transcriber` trait: Parakeet TDT 0.6b v3 int8 ONNX
  (the files V1 already downloaded) and whisper small (`ggml-small.bin`).
- V1's measured lessons carried over: near-silence and VAD gates, trim to the
  voiced span, quiet clips scaled to RMS 0.05, CPU-only Parakeet, bounded model
  calls (20 s pieces), language never forced.
- Whisper's own doubt drops its output (no-speech > 0.6, mean token log
  probability < −1, non-Latin script), so noise is not typed.
- `cargo run --release --bin banc` replays `~/.whispy/lost/`, a synthetic
  reference set with known text (macOS `say`, FR/EN, short to long, plus V1's
  validation fixtures), the same references at the level of real lost
  dictation, and non-speech; per engine × strategy (raw, gated, louder, padded,
  each alone or with the other engine as fallback) it reports text rate, WER,
  latency p50/p95, runs V1 on the same clips, measures a 180 s dictation's
  memory, and writes `v2/bench/REPORT.md` with the pick.
- The library default is the bench's pick: **Parakeet, then whisper when
  Parakeet returns nothing, strategy `louder`**. The bench exits 2 if they
  ever differ.
- CI: a `v2` job on macOS runs `cargo fmt --check`, `cargo test` and
  `cargo clippy -D warnings`.

## Measured (v2/bench/REPORT.md, 2026-10-16)

| configuration | lost: text | ref WER | quiet WER | invented | p95 ~5 s | 180 s peak RSS |
|---|---|---|---|---|---|---|
| V1 | 0/20 | 3.4% | 6.3% | 0 | 0.11 s | 1600 MB (change bound-model-input) |
| parakeet / louder | 2/20 | 3.7% | 6.3% | 0 | 0.13 s | 1090 MB |
| whisper / louder | 5/20 | 6.7% | 11.9% | 0 | 0.54 s | 741 MB |
| **parakeet then whisper / louder** (pick) | **5/20** | **3.7%** | **6.3%** | **0** | **0.13 s** | **1721 MB** |

Card criteria, said plainly:
- **3 is not met.** 5/20 lost clips get text against 70 % asked. With
  whisper's doubt filter off, 13/20 « got text », but most of it was noise
  turned into Georgian, Khmer or English nonsense; the 15 clips left come back
  empty from both engines (eight of them are one 16:32 burst of ~8 s clips).
  The three tries of card #2's sentence are all recovered, plus one more short
  French dictation and one two-word English one. Reference WER is 3.7 % against
  V1's 3.4 %: the port returns V1's exact text on 48 of 50 speech clips; one
  difference is punctuation, the other is « GitHub », wrong in both (« JEB »
  for V1, « J-Eub » for V2, which the hyphen makes two wrong words). The mel
  features match V1's to 2·10⁻⁵; the gap is inference numerics, not a bug.
- **5 is met per engine, not by the pick.** Parakeet alone 1090 MB (V1:
  1600 MB), whisper alone 741 MB, both loaded 1721 MB.
- **7 is met.** **4** (transcription part only): p95 0.13 s; a fallback adds
  ~0.5 s.

## Raison d'être

- **Usage:** every dictation, many times a day; the bench every time an engine
  or strategy changes.
- **Without it:** V1 keeps dropping short and quiet speech, and the user
  repeats themselves.

## Refusé

- **`transcribe-rs` for Parakeet** — ignores the TDT duration head (decodes
  unlike V1) and needs a preprocessor file V1's cache lacks.
- **`sherpa-onnx`/`sherpa-rs`** — needs its own model conversion, a new
  download.
- **A « context » complement** (prepending carrier speech, cutting it out by
  timestamp) — a voice unlike the user's and a cut that can eat the first
  word; the silence complement (`padded`) is measured instead.
- **Lowering the 70 % threshold** — not ours to move; the numbers are reported
  as they are.
- **The app half** (menu bar, Fn, insertion) — next PR.

## Coût

- `ort =2.0.0-rc.10` (ONNX Runtime 1.22, CPU provider): runs Parakeet; the
  build downloads ORT's prebuilt library once (pyke CDN), nothing at run time.
- `whisper-rs =0.16.0` with `metal`: whisper.cpp; Metal halves latency
  (~1.2 s → ~0.5 s per clip) at the same footprint. Builds with `cmake`.
- `webrtc-vad =0.4.0`: the very VAD V1's gates were calibrated on.
- `rustfft =6.4.1`: the FFT of the NeMo mel features.
- `hound =3.5.1`: WAV in and out (lost clips, references, V1 replay).
- `libc` (bench only, already transitive): peak RSS and physical footprint.
- No network call at run time; models are the files already on the Mac and a
  missing one is an error, not a download.
- Repository weight: 2.4 MB of reference WAVs.

## Capabilities

### New Capabilities
- `v2-transcription-core`: PCM → text for Whispy V2 — engines, gates,
  bounded calls, fallback, defaults chosen by the bench, and the bench itself.

### Modified Capabilities
_None._ V1 is untouched.

## Impact

- New: `v2/` (workspace, library, bench, reference clips, report).
- `.github/workflows/ci.yml`: new `v2` job; Python jobs unchanged.
- V1 code, install and `~/.whispy/lost/` untouched (the V1 replay disables
  lost-clip keeping and runs offline with a private TMPDIR).

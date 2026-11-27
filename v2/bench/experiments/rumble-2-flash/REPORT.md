# Rumble-2-Flash vs Parakeet for French dictation

Experiment for issue #66, run on 2026-11-27 on an Apple M1 Pro (32 GB). Nothing in
Whispy's shipped code changed: the bench binary (`banc --transcribe`) ran
Parakeet, and a separate Python environment ran Rumble-2-Flash.

**Recommendation: keep it as an option, do not integrate now.** Rumble-2-Flash
makes clearly fewer errors than Parakeet (9.6 % WER vs 13.0 %; 6.9 % vs 11.2 % on
real voices), but it is neither faster nor lighter. The issue's success criterion
("WER ≤ Parakeet **and** latency ≤ Parakeet, or clearly lighter at equal
accuracy") is not met. The latency gap (~0.1–0.15 s per sentence) would not be
noticed in dictation. The memory gap (about ×2 to ×3) and the lack of an official
Rust runtime matter more. The next step that would justify integration is
Rumble-2-Flash exported to ONNX int8 and run through `ort` (see the end of this report).

## The model, checked on its official page

[Reson8/Rumble-2-Flash](https://huggingface.co/Reson8/Rumble-2-Flash): Apache
2.0, 45 languages (the press said "40+"), French included. The badge says 0.5B
parameters. It is a fine-tune of `Qwen/Qwen3-ASR-0.6B`, the Qwen3-ASR
architecture: an audio encoder followed by an autoregressive LLM decoder. It is
not a transducer like Parakeet. The Hugging Face repository was created on
2026-10-14. The model card cites Open ASR Leaderboard results dated 2026-11-18,
which matches the announcement date the aggregators give. Supported runtimes are
Transformers and vLLM, with no `trust_remote_code`. The weights are
`model.safetensors` in bf16 (1.02 GB) plus an optional CTC head (357 MB).

## Corpus (40 clips, no personal data)

- **`tts` (20)**: the 20 sentences in [`sentences.txt`](sentences.txt), written
  for this test: French dictation with English tech jargon (pull request,
  Kubernetes, Redis, feature flag, cargo clippy…). Synthesized with macOS `say`,
  alternating the Thomas and Jacques voices, as 16 kHz mono WAV.
- **`fleurs` (20)**: real voices, the first 20 distinct utterances under 15 s of
  the French FLEURS test split (`google/fleurs`, `fr_fr`), as a control.
  [`fleurs_extract.py`](fleurs_extract.py) extracts them.

No user dictation (`~/.whispy/`) was used. The audio is not committed: the
scripts regenerate it.

## Configurations

| Engine | Runtime | Notes |
|---|---|---|
| Parakeet TDT 0.6b v3 | ONNX Runtime, int8, CPU (`ort`, Whispy's) | `banc --transcribe parakeet padded`: Whispy's default engine and strategy, without the whisper fallback (never triggered here: no clip came back empty) |
| Rumble-2-Flash | Transformers 5.24.1 + PyTorch 2.15, fp16, MPS (Apple GPU) | French forced (`language="French"`), greedy, `digits` left at its default |
| Rumble-2-Flash | same, language auto-detected | |
| Rumble-2-Flash | same, fp32, CPU | for a like-for-like comparison with Parakeet on CPU |

Latency = one clip's preprocessing + inference, model warm (one warm-up clip
first). WER is computed after normalization: lowercase, punctuation dropped,
digits spelled out in French. Both engines write "14h" or "500", which would
otherwise count as errors (see [`score.py`](score.py)).

## Results

| Model | Set | WER | Median latency | p95 latency | RTF |
|---|---|---|---|---|---|
| Parakeet (Whispy, ONNX int8, CPU) | tts (20) | 16.4 % | 0.17 s | 0.18 s | 0.038 |
| Parakeet (Whispy, ONNX int8, CPU) | fleurs (20) | 11.2 % | 0.28 s | 0.38 s | 0.027 |
| **Parakeet (Whispy, ONNX int8, CPU)** | **all (40)** | **13.0 %** | **0.18 s** | **0.38 s** | **0.031** |
| Rumble-2-Flash (French forced, MPS fp16) | tts (20) | 14.7 % | 0.23 s | 0.30 s | 0.055 |
| Rumble-2-Flash (French forced, MPS fp16) | fleurs (20) | 6.9 % | 0.38 s | 0.49 s | 0.040 |
| **Rumble-2-Flash (French forced, MPS fp16)** | **all (40)** | **9.6 %** | **0.32 s** | **0.49 s** | **0.045** |
| Rumble-2-Flash (auto language, MPS fp16) | all (40) | 10.8 % | 0.28 s | 0.51 s | 0.046 |
| Rumble-2-Flash (French forced, CPU fp32) | all (40) | 9.6 % | 1.65 s | 3.36 s | 0.269 |

| | Parakeet (Whispy) | Rumble-2-Flash |
|---|---|---|
| Weights on disk | 670 MB (int8 ONNX) | 1.02 GB (bf16 safetensors), +357 MB CTC head |
| Peak memory of the process (RSS) | 1.08 GB | 2.2–3.4 GB (MPS fp16), 3.0 GB (CPU fp32) |
| Model load, from local cache | ≈ 2 s | 1.7–2.1 s |
| Rust runtime | `ort`, already in Whispy | none official (see below) |

Raw transcripts are in [`results/`](results/), and the per-clip diff in
[`results/score.out`](results/score.out).

## What the transcripts show

- **Real voices: Rumble is clearly better** (6.9 % vs 11.2 %), on general French
  vocabulary.
- **Tech jargon: a draw, both struggle** (14.7 % vs 16.4 %). Rumble gets "pull
  request", "Docker", "PostgreSQL", "warnings" and "mettre à jour" right, where
  Parakeet wrote "poule request", "bloquer", "postgres condra" and "mettre vour".
  Both still fail on "endpoint", "React", "linter", "GitHub Actions" and
  "webhook Slack". The synthetic voice probably makes this set harder than a real
  dictation.
- **Auto-detected language is risky**: on one clip (`tts-10`, French with
  "ONNX Runtime"), Rumble switched to German and produced a German-sounding transcript ("modell der erkenntnisse lokal…").
  Whispy would have to force the language, and therefore know it.
- Rumble adds French typography (a space before `?`) and keeps the digits:
  Whispy's French-number post-processing would need checking against it.

## Rust integration feasibility

- No official ONNX, GGUF or candle export. The model card targets Transformers and vLLM.
- Since the model is a Qwen3-ASR-0.6B fine-tune, community tools for that
  architecture should apply, but nobody has tested them on Rumble:
  [ONNX exports of Qwen3-ASR-0.6B](https://huggingface.co/OpenVoiceOS/qwen3-asr-0.6b-onnx)
  (`onnx-asr` "speech-llm" path, int8 included, with architecture-specific
  patches), and Rust crates (`qwen3-asr-rs` over libtorch, `qwen-asr` CPU-only).
  A candle port is said to be waiting for review.
- An autoregressive decoder means a generation loop with a KV cache to write
  around `ort`, much more than Parakeet's TDT decoder. Estimate: a few days of
  work, against one for an engine already in ONNX.

## Limits of this experiment

- Different runtimes: Parakeet runs int8 on CPU through ONNX Runtime, while
  Rumble runs fp16 on the GPU through PyTorch. An int8 ONNX export of Rumble could
  close part of the latency and memory gap. On CPU in fp32, Rumble is about 9×
  slower than Parakeet.
- Small samples (40 clips): the WER gap on FLEURS (≈ 4 points over 20 sentences)
  is a signal, not a proof. The `tts` set is synthetic.
- The RSS under MPS does not fully count unified GPU memory. The first run (with
  the download) peaked at 3.4 GB, a later run at 2.2 GB.

## Reproduce

```bash
# Python 3.12 env: torch transformers accelerate soundfile librosa jiwer num2words pyarrow
# corpus: say -v Thomas|Jacques -o tts-NN.wav --data-format=LEI16@16000 "<sentence>" (+ tts-NN.txt)
python -I fleurs_extract.py fleurs-fr_fr-test.parquet corpus/
(cd corpus && ../../../../target/release/banc --transcribe parakeet padded tts-01.wav tts-*.wav fleurs-*.wav) > results/parakeet.tsv
python -I rumble.py mps French corpus/ > results/rumble-mps.tsv     # also: mps auto, cpu French
python -I score.py corpus/ results/ diff > results/score.out
```

# ASR bench

Throwaway-quality measurements, kept because re-deriving them costs an hour and
re-running them costs a minute. These are the scripts behind the numbers in
`CHANGELOG.md` (the Parakeet migration and the speech gate) and in
`docs/transcription-quality-and-memory.md`.

Not part of the test suite: they need `say`/`sox`, they take minutes, and several
need an interpreter with the *previous* backend installed. Assertions that must
hold on every run live in `tests/` instead — `tests/test_transcription_quality.py`
for the real-model tier, `tests/test_audio.py` and `tests/test_segmentation.py`
for the gates.

## Requirements

- macOS with `say`, and `sox` (`brew install sox`)
- the project venv, for everything measuring the current backend
- a throwaway venv with `faster-whisper`, for the two comparison scripts

Artifacts go to `$TMPDIR/whispy-asr-bench` (override with `BENCH_OUT`), never into
the repo.

## Running

```bash
# Corpus first — everything else reads its manifest.
./.venv/bin/python scripts/asr-bench/make_clips.py

# Current backend.
./.venv/bin/python scripts/asr-bench/run_parakeet.py

# Previous backend, for comparison. Separate venv on purpose: faster-whisper is
# not a project dependency any more and should not be reinstalled into .venv.
python3 -m venv /tmp/fw-venv && /tmp/fw-venv/bin/pip install faster-whisper
/tmp/fw-venv/bin/python scripts/asr-bench/run_whisper.py

# WER + latency + the bug cases, side by side.
./.venv/bin/python scripts/asr-bench/compare.py
```

## What each script answers

| Script | Question | Interpreter |
|---|---|---|
| `make_clips.py` | — (builds the corpus and manifest) | project venv |
| `run_parakeet.py` | How does the current backend do on it? | project venv |
| `run_whisper.py` | How did the previous one do on the same clips? | faster-whisper venv |
| `compare.py` | WER, latency, and the three bug cases, side by side | project venv |
| `verify_long.py` | Is the old backend's long-clip truncation real, or a mis-consumed generator? | faster-whisper venv |
| `probe_noise_rate.py` | How often does loud non-speech become text, and does the speech gate stop it? | project venv |
| `probe_vad_seconds.py` | Why does the speech gate measure voiced seconds instead of a ratio, and where does it stop working? | project venv |
| `probe_logprobs.py` | Could token confidence reject invented short output? (no) | project venv |
| `probe_chunk_language.py` | Does streaming segmentation, not language detection, make a French dictation come back partly in English? | project venv |
| `probe_chunk_merge.py` | How much surrounding speech does a too-short chunk need before the language is right again? | project venv |

## Measured on an Apple M1 Pro

Numbers move with the machine; the *shapes* are the point.

- **Latency** — 6-16x faster, and proportional to audio length instead of flat.
  Whisper padded every input to a 30s window, so a 0.5s chunk and a 3s chunk both
  cost ~0.6s. Parakeet: 0.035s and 0.11s.
- **WER** — 5.2% against 17.2% for the old defaults (which forced `language="en"`),
  3.4% against Whisper with language detection left on.
- **Long recordings** — a 16.6s clip came back as one sentence from Whisper under
  all four decoder configurations tried, ~87% of the audio dropped with no error.
  Parakeet returns all of it.
- **Forced language** — French speech with `language="en"` came back translated
  into English rather than recognized. Nothing forces a language now.
- **Non-speech above the RMS gate** — Parakeet answered 3 of 100 noise
  realizations with a filler, Whisper 52-100% depending on noise type. The speech
  gate took Parakeet's 3 to 0.
- **Confidence gating** — unusable. An invented `Hello` on a mid-word cut scores
  mean logprob -0.040; a correctly recognized `Oui.` scores -0.399.

## Caveats worth knowing before trusting a run

- `say` output is not byte-stable between runs, so a single clip can flip a
  borderline result. Anything marginal needs N realizations, not one.
- `say` voices are not equally good. The alphabetically-first macOS voices are
  legacy novelty ones whose synthesis the model legitimately fails on; `_bench`
  picks modern voices for this reason.
- `sox synth` draws fresh noise per call unless `-R` is passed. For a rate, that
  is what you want; for a regression test, it is a flaky test generator.
- Synthetic TTS is not real dictation. These scripts compare backends against
  each other on identical audio, which is what they are good for. They do not
  measure real-world accuracy.

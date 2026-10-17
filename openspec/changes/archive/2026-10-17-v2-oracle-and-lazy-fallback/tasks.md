## 1. Lazy fallback (`v2/whispy-core`)

- [x] 1.1 `Lazy` transcriber: load on first call, free after `FALLBACK_IDLE`, reaper thread only while loaded
- [x] 1.2 `EngineKind::lazy` checks the model file up front; `Pipeline::load_default` uses it for whisper
- [x] 1.3 Unit tests: nothing loaded before the first call, one load per idle spell, freed then reloaded, failed load retried

## 2. Oracle (`v2/bench`)

- [x] 2.1 `oracle.py`: whisper large-v3-turbo (MLX) classes lost clips speech / doubtful / no speech
- [x] 2.2 Clip copies and `listen.html` in the gitignored `bench/oracle/`; verdicts copied to `verdicts.tsv`
- [x] 2.3 `banc` reads classes and verdicts; « lost speech » and « WER vs oracle » columns; pick order uses them first

## 3. Memory (`v2/banc`)

- [x] 3.1 Lazy probe: 180 s dictation, two reprises Parakeet is made to miss, 32 s quiet; normal peak, reprise peak, first-load latency, release
- [x] 3.2 Criterion 5 section in `REPORT.md` from that probe

## 4. Delivery

- [x] 4.1 Bench rerun, `REPORT.md` refreshed
- [x] 4.2 `v2/README.md`: lazy fallback, oracle workflow
- [x] 4.3 `cargo fmt --check`, `cargo test`, `cargo clippy -D warnings` green

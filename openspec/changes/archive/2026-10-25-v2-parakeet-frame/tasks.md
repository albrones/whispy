## 1. Core (`v2/whispy-core`)

- [x] 1.1 Parakeet input framed by 0.25 s of digital silence
- [x] 1.2 An answer without a letter or digit is empty; the fallback tries (unit test)
- [x] 1.3 Default strategy set to the bench's pick (`padded`)

## 2. Delivery

- [x] 2.1 `banc --labelled`: criterion 3 holds; full bench rerun, `REPORT.md` refreshed; latency test rerun
- [x] 2.2 `v2/README.md`: frame, empty answers, default, latency
- [x] 2.3 `cargo fmt --check`, `cargo test`, `cargo clippy -D warnings` green

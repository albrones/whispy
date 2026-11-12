## 1. Bench

- [x] 1.1 `v2/banc/src/labelled.rs`: label and baseline parsing, V1-compatible word normalization, scoring, verdict
- [x] 1.2 `banc --labelled [dir]` in `main.rs`; exit without running static destructors (whisper's Metal teardown asserts at exit)
- [x] 1.3 cargo tests for parsing, normalization, scoring and the 70 % rule
- [x] 1.4 README: how to run it, what it prints

## 2. Proof

- [x] 2.1 Run it on `~/.whispy/bench` and report the three parts

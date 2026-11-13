## 1. Bench

- [x] 1.1 Replay the reviewed labelled clips through a whole `Pipeline` per configuration; V1's side comes from `baseline.json`
- [x] 1.2 Build the criterion 3 verdict per configuration
- [x] 1.3 Rank the pick on it; unlabelled lost clips only without labelled clips
- [x] 1.4 Count an answer without a letter or digit as empty, as the pipeline does
- [x] 1.5 Report: per-configuration table, pick line, criterion 3 line; counts only

## 2. Proof

- [x] 2.1 Unit tests of the rule (`banc` `report`)
- [x] 2.2 `cargo run --release --bin banc` exits 0 and `bench/REPORT.md` names the default
- [x] 2.3 README and spec updated

## 1. Instruments (PR 1)

- [x] 1.1 Log a successful transcription at INFO with duration and text length, never the text
- [x] 1.2 Keep each lost clip in `~/.whispy/lost/` (newest 20), named in the `Lost speech` warning
- [x] 1.3 `scripts/replay_lost.py`: untouched, Whispy trim, 1 s margin, gain-normalized
- [x] 1.4 Tests: kept and named, oldest pruned, success logged without text; tests never write to the real home

## 2. Diagnosis and fix (PR 2, after at least 10 real lost clips)

- [x] 2.1 Replay the kept clips and write the result table and the measured cause (in `design.md`: `research/` is gitignored)
- [x] 2.2 Fix the cause in the transcription path, with one test that fails without the fix
- [x] 2.3 Replay after the fix: text for 4/4 clear-speech clips (criterion 5 restated in design.md); `make test` green

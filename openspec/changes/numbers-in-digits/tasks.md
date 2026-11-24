## 1. Core (Otto)

- [x] 1.1 `itn` module: cardinals and compounds, « pour cent », hours and minutes, « un » / « une » kept, English untouched
- [x] 1.2 `Pipeline::transcribe` normalises; `transcribe_raw` for the streamer
- [x] 1.3 `Streamer` normalises the committed text, holds a trailing number back, flushes at the stop; the caption in digits
- [x] 1.4 Tests: the 24/11 sentence, compounds, words that stay, English, any two cuts equal the block, `quatre-vingt` | `-dix`, `quatorze heures` | `trente`

## 2. Bench (Otto)

- [x] 2.1 Reference clips with numbers (4 French, 1 English) in `manifest.tsv` and `generate.sh`
- [x] 2.2 WER after normalisation (`wer`, `labelled`); labelled WER no worse than 15.1 %, bench exits 0
- [x] 2.3 180 s dictation under 1.5 GB

## 3. Docs

- [x] 3.1 One line in `v2/README.md`

## 4. Delivery (Ernesto)

- [x] 4.1 Gate green (fmt, clippy, tests)
- [ ] 4.2 [manual] The 24/11 sentence in toggle mode with Type while speaking arrives in TextEdit with digits
- [ ] 4.3 Archive

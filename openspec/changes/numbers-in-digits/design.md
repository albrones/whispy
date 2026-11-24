## Context

Parakeet writes numbers in words. The text leaves `whispy-core` by two paths: `Pipeline::transcribe` (block, hold, and the open audio sent whole) and `Streamer`, which types passages and re-joins them.

## Decisions

- **Own ITN, no crate** (`whispy-core/src/itn.rs`): a left-to-right reader of number words (units, teens, tens, « quatre-vingt », « cent », « mille », « et » in « vingt et un »), then the words that decide its form: « pour cent », « heures » plus minutes. A lone « un » / « une » is never a number; inside a compound it is.
- **Language is not passed in.** Only French number words trigger anything, so English passes through. « six », « sept » and « cent » exist in English: alone, they stay in letters when an English function word (« the », « and », « I »…) is the word before or after.
- **Block path:** `Pipeline::transcribe` normalises the joined text. `transcribe_raw` skips it: the streamer uses it so it can join first.
- **Live path, no number cut:** the streamer keeps the committed text raw, normalises the whole, and types the difference with what it already typed. `itn::stable_prefix_len` holds back the trailing number or a word that may continue one (`et`, `pour`), so normalising the stable prefix is always the start of normalising the whole; the stop flushes the rest. The joined passages therefore equal one block, whatever the cuts (tested on every pair of cuts of several sentences).
- **Hyphen cut:** a token starting with `-` after a number word is glued to it before reading.
- **Caption:** `Streamer::committed()` and the provisional words are normalised too, at no cost.
- **Bench:** `wer::normalized_words` and `labelled::v1_words` normalise numbers on both sides, so a reference written as spoken still meets digits. Idempotent, so already-normalised text is stable.

## Known limits

- « mille et une » reads « 1000 et une »; no decimals (« virgule »); no ordinals; years like « dix-neuf cent » read 1900.
- « deux heures trois tests » would read « 2 h 03 tests » (minutes are taken greedily).
- A number at the very end of what is spoken is typed at the next commit or at the stop, not before.

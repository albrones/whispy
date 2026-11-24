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

- **Guards:** every number is in digits unless English is around. « six », « sept », « cent », « million » stay in letters with an English function word within three tokens in the same clause (« I will take six. »); a singular « million » after a number is English (« six million dollars »); « cents » and « vingts » never start a number. The adjective « neuf » stays in letters after « tout » or « du », after « de » ending the clause, and after a noun with an article before it (« un pull neuf »).
- **Held numbers:** what a guard rejects now is still held back at the end of a passage, and a number shared with English waits for three more words or the end of the clause, since the next words may change the verdict (« the cent » | « vingt »). Text already typed is never typed again.
- **Stop:** the held tail is typed on every way out: a normal stop, a deaf take, no engine loaded, an engine error (the audio is then kept as a lost clip).
- **Bench:** `numbers.rs` checks V2's own text for the digits of the number clips (and that the English clip stays in letters) and the bench exits non-zero otherwise; the WER alone cannot see it, since it reads numbers in digits on both sides.

## Known limits

- Minutes are taken greedily (« deux heures cinq personnes » reads « 2 h 05 personnes »).
- « Sept. » (abbreviation), proper names (« Louis Quatorze »), decimals (« virgule »), ordinals; years like « dix-neuf cent » read 1900; numbers are written without a thousands separator.
- A number at the very end of what is spoken is typed with the next word or at the stop, not before.

## Accepted after review (follow-up, Régie idea card)

- Two ambiguous numbers within three words, with an English word after the second (« il y a six chats six the »), can break « joined = one block » in live typing: the first one's window reaches past the hold. Rare, mixed-language only.
- « four » sits in the English word list, so « six pains au four » keeps « six » in letters.

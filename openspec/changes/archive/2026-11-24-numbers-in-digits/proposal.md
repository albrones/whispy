## Why

Parakeet always writes numbers in words. In the manual test of 2026-11-24 (Type while speaking), « ajouter 3 tests… sous 2 secondes… le 12 décembre à 14 h 30 » came out « ajouter trois tests… sous deux secondes… le douze décembre à quatorze heures trente ». The user wants digits.

## What Changes

- A French inverse text normalisation (ITN) step in `whispy-core` turns spoken numbers into digits after transcription, always on (no setting), for every dictation: one block, hold, and each passage typed live by « Type while speaking ».
- Covered: cardinals including compounds (« soixante-dix » → 70, « quatre-vingt-dix-sept » → 97, « deux mille vingt-six » → 2026), times (« quatorze heures trente » → « 14 h 30 »), dates (« le douze décembre » → « le 12 décembre »), percentages (« dix pour cent » → « 10 % ») and numbers before units (« deux secondes » → « 2 secondes »).
- « un » / « une » stay in letters (ambiguous article: « un peu », « une fois », « l'un des », « il y en a un »); every other number becomes digits (« deux ou trois choses » → « 2 ou 3 choses »).
- Live typing never splits a number across two passages (« quatre-vingt » | « -dix »): a passage that ends on a word that can continue a number holds that word back until the next pass, so the live text joined equals the one-block text.
- The bench adds reference cases with numbers and measures WER after normalisation.

## Capabilities

### Modified Capabilities
- `v2-transcription-core`: transcribed text is normalised to digits before it leaves the pipeline and the rolling commit.

## Acceptance criteria

1. The Parakeet string « ajouter trois tests sous deux secondes le douze décembre à quatorze heures trente » comes out « ajouter 3 tests sous 2 secondes le 12 décembre à 14 h 30 ».
2. Compounds come out in digits: « soixante-dix » → 70, « quatre-vingt-dix-sept » → 97, « deux mille vingt-six » → 2026; « dix pour cent » → « 10 % ».
3. Words that do not count stay in letters: « un peu », « une fois », « l'un des », « il y en a un » are unchanged.
4. The conversion applies in one block, in hold and to each passage typed live; a number is never split between two passages (« quatre-vingt » | « -dix ») and the live-typed text, joined, equals the one-block text.
5. The bench adds reference cases with numbers and measures WER after normalisation; on the labelled clips, V2's WER is no worse than before (15.1 %) and the bench still exits 0.
6. The v2 gate is green (fmt, clippy, tests); a 180 s dictation stays under 1.5 GB.
7. [manual] Dictating the 24/11 test sentence in toggle mode with Type while speaking, it arrives in TextEdit with digits.

## Impact

- `v2/whispy-core`: new ITN module; called from the pipeline's output and from the rolling commit in `stream`.
- `v2/banc`: number reference cases; WER after normalisation.
- English dictation is untouched (the ITN applies to French text only).

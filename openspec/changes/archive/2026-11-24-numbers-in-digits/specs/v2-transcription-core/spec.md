## ADDED Requirements

### Requirement: Spoken numbers are written in digits
V2 SHALL turn the French numbers in a transcript into digits before the text leaves the core, for every dictation: one block, hold, the open audio sent whole through the default pipeline, and every passage typed by « Type while speaking ». Cardinals and their compounds SHALL become digits (« soixante-dix » 70, « quatre-vingt-dix-sept » 97, « deux mille vingt-six » 2026), « pour cent » after a number SHALL give « N % », and « heures » after a number SHALL stay a word (« quatorze heures » « 14 heures »), or become « H h MM » when minutes follow (« quatorze heures trente » « 14 h 30 »). « un » and « une » SHALL stay in letters unless they end a compound (« vingt et un » 21). The rewrite SHALL be always on, with no setting. Text without French number words, English included, SHALL be unchanged; « six », « sept » and « cent » beside an English function word SHALL be left alone.

#### Scenario: The Parakeet sentence of the 24/11 manual test
- **WHEN** Parakeet writes « ajouter trois tests sous deux secondes le douze décembre à quatorze heures trente »
- **THEN** the text SHALL be « ajouter 3 tests sous 2 secondes le 12 décembre à 14 h 30 »

_Tier: unit — `whispy-core` `itn`._

#### Scenario: Compounds and percentages
- **WHEN** the text holds « soixante-dix », « quatre-vingt-dix-sept », « deux mille vingt-six » and « dix pour cent »
- **THEN** they SHALL read 70, 97, 2026 and « 10 % »

_Tier: unit — `whispy-core` `itn`._

#### Scenario: Words that do not count stay in letters
- **WHEN** the text is « un peu », « une fois », « l'un des » or « il y en a un »
- **THEN** it SHALL be unchanged, while « deux ou trois choses » SHALL read « 2 ou 3 choses »

_Tier: unit — `whispy-core` `itn`._

#### Scenario: English is untouched
- **WHEN** the text is « I have six apples » or « ten per cent of the total »
- **THEN** it SHALL be unchanged

_Tier: unit — `whispy-core` `itn`._

### Requirement: A number is never split between two typed passages
While a dictation is typed while spoken, the text committed so far SHALL be normalised as a whole, and a trailing number, or a word that may continue one (« et », « pour »), SHALL be held back until what follows is known or the dictation stops. A word starting with a hyphen that carries on a number word (« quatre-vingt » « -dix ») SHALL be read as one number. The passages typed, joined in order, SHALL equal the text of the same words normalised in one block.

#### Scenario: Cut inside a compound
- **WHEN** the passes commit « Ajoute moi les quatre-vingt » and the stop then hears « -dix tests sous demain »
- **THEN** the first passage typed SHALL be « Ajoute moi les » and all the passages joined SHALL be « Ajoute moi les 90 tests sous demain », the text of one block

_Tier: unit — `whispy-core` `stream`, with a scripted timed engine._

#### Scenario: Cut between hours and minutes
- **WHEN** the passes commit « Rappelle moi à quatorze heures » and the stop then hears « trente chez Paul »
- **THEN** the passages joined SHALL be « Rappelle moi à 14 h 30 chez Paul », the text of one block

_Tier: unit — `whispy-core` `stream`._

#### Scenario: Any cut of a sentence
- **WHEN** a sentence is released in two passages cut at any two word boundaries
- **THEN** the passages joined SHALL equal the sentence normalised in one block

_Tier: unit — `whispy-core` `itn`._

### Requirement: The bench scores V2 after number normalisation
The bench SHALL read the numbers of the expected text and of V2's text in digits before counting word errors, and its reference clips SHALL include French clips with numbers and an English clip with number words. On the user's labelled clips V2's word error rate SHALL be no worse than before this change, and the bench SHALL still exit 0.

#### Scenario: A reference written as spoken meets V2's digits
- **WHEN** the expected text is « le train de huit heures » and V2 returns « le train de 8 heures »
- **THEN** no word error SHALL be counted

_Tier: unit — `banc` `wer`; the labelled WER is measured on the Mac._

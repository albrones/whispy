## ADDED Requirements

### Requirement: Parakeet gives each word its time in the audio
Parakeet SHALL return, on request, the words of its transcript with their start and end time in the input samples, read from the TDT decoder's encoder frames (80 ms each), with the silence it adds in front subtracted and every time within the input's duration. The words' texts joined by single spaces SHALL equal the plain transcript of the same input. An engine without timings SHALL say so rather than invent them.

#### Scenario: Times follow the speech
- **WHEN** Parakeet transcribes a French reference sentence with its timings
- **THEN** the words SHALL equal the plain transcript joined by spaces, their start and end times SHALL never decrease, and the last end SHALL be within the clip

_Tier: unit when the model is on the Mac — `whispy-core` `parakeet`._

### Requirement: A dictation typed while spoken is committed sentence by sentence
While a dictation is typed while spoken, V2 SHALL re-transcribe the open window (the audio since the last commit) with timings at least every 0.6 s of new audio when it holds speech, and SHALL commit text only where two consecutive passes agree word for word. A sentence SHALL be committed when it is stable up to its final `.`, `?`, `!` or `…` and either more words follow it or 2 s of silence do; its audio SHALL then be released at the middle of the gap after its last word. A window reaching 15 s without a committable sentence SHALL be committed at its longest stable pause, and the next text SHALL continue that sentence (first letter lowered unless an acronym). No engine call SHALL receive more than 20 s: past it, the window SHALL go through the full default pipeline and be committed whole. At the stop, the open window SHALL go through the full default pipeline. Every committed text and the stop's text joined in order SHALL be the dictation's text, each audio sample transcribed into exactly one committed text. Each pass SHALL log its counts (window length, pass time, words, stable words, committed words, forced or not) and no dictated text.

#### Scenario: A sentence followed by speech is committed
- **WHEN** two passes agree on « Je vais envoyer le rapport. Pense » and the audio goes on
- **THEN** « Je vais envoyer le rapport. » SHALL be committed and the window SHALL start in the gap before « Pense »

_Tier: unit — `whispy-core` `stream`, with a scripted timed engine._

#### Scenario: A provisional period is not committed
- **WHEN** a pass ends with « on pourrait faire. » and the next pass, after more speech, reads « on pourrait faire vraiment de l'affichage. »
- **THEN** nothing up to « faire » SHALL have been committed with a period

_Tier: unit — `whispy-core` `stream`._

#### Scenario: A run-on window is bounded
- **WHEN** 25 s of speech arrive without a sentence end
- **THEN** a forced commit SHALL happen by 15 s at the longest stable pause, no engine call SHALL receive more than 20 s, and the joined text SHALL hold every word once

_Tier: unit — `whispy-core` `stream`._

#### Scenario: Silence costs nothing
- **WHEN** 10 s of silence follow a committed sentence
- **THEN** no engine call SHALL be made during them

_Tier: unit — `whispy-core` `stream`._

#### Scenario: The bench compares the three ways
- **WHEN** `banc --streaming` runs
- **THEN** it SHALL report, for one block, the pieces cut at pauses and the rolling re-transcription, on the reference clips and the user's labelled speech clips of 8 s or more: WER, extra sentence ends against one block, commit delay p50/p95, stop latency p50/p95 and mean pass cost; and SHALL exit 1 when a criterion of the change fails

_Tier: bench._

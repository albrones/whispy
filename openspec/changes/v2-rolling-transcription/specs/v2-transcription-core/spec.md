## ADDED Requirements

### Requirement: Parakeet gives each word its time in the audio
Parakeet SHALL return, on request, the words of its transcript with their start and end time in the input samples, read from the TDT decoder's encoder frames (80 ms each), with the silence it adds in front subtracted and every time within the input's duration. The words' texts joined by single spaces SHALL equal the plain transcript of the same input. An engine without timings SHALL say so rather than invent them.

#### Scenario: Times follow the speech
- **WHEN** Parakeet transcribes a French reference sentence with its timings
- **THEN** the words SHALL equal the plain transcript joined by spaces, their start and end times SHALL never decrease, and the last end SHALL be within the clip

_Tier: unit when the model is on the Mac — `whispy-core` `parakeet`._

### Requirement: A dictation typed while spoken is committed word by word, in context
While a dictation is typed while spoken, V2 SHALL re-transcribe its window, about 3 s already typed (starting in a gap between words) followed by the audio not yet typed, with timings at least every 0.6 s of new audio when it holds speech, and SHALL drop the words heard in the typed part. It SHALL commit a word only where two consecutive passes agree word for word up to it, and only once the model has heard 1.5 s of audio past it with more words following, or 2 s of silence when none follows. After a pause of 2 s or more with nothing pending, the audio before it SHALL be closed (silence with no engine call; any voiced sound through the full default pipeline, fallback included) and what follows heard without the typed context. No engine call SHALL receive more than 20 s: before that, the untyped audio SHALL go through the full default pipeline and be committed whole. At the stop, the untyped audio SHALL be transcribed once more in its context, or through the full default pipeline when there is no context or that hears nothing. Every committed text and the stop's text joined in order SHALL be the dictation's text, each word typed exactly once. Each pass SHALL log its counts (window length, pass time, words, stable words, committed words, overflow or not) and no dictated text.

#### Scenario: A word heard far enough past is committed
- **WHEN** two passes agree on « Je vais envoyer le rapport. Pense » and the model has heard 2.1 s past « rapport. » but only 1.2 s past « Pense »
- **THEN** « Je vais envoyer le rapport. » SHALL be committed, « Pense » SHALL stay provisional, and the next window SHALL keep the typed audio before it as context

_Tier: unit — `whispy-core` `stream`, with a scripted timed engine._

#### Scenario: A provisional period is not committed
- **WHEN** a pass ends with « on pourrait faire. » at a 1.2 s pause and the next pass, after more speech, reads « on pourrait faire vraiment de l'affichage. »
- **THEN** « faire. » SHALL never be committed with its period

_Tier: unit — `whispy-core` `stream`._

#### Scenario: Every word once, in order
- **WHEN** a 30-word dictation with pauses is streamed 50 ms at a time to an engine that hears the audio it is given
- **THEN** the typed text SHALL be the 30 words once each in order, typed in at least five commits while spoken, and no engine call SHALL receive more than 20 s

_Tier: unit — `whispy-core` `stream`._

#### Scenario: Silence costs nothing
- **WHEN** 10 s of silence follow a committed sentence
- **THEN** no engine call SHALL be made during them

_Tier: unit — `whispy-core` `stream`._

#### Scenario: The bench compares the three ways
- **WHEN** `banc --streaming` runs
- **THEN** it SHALL report, for one block, the pieces cut at pauses and the rolling re-transcription, on the reference clips and the user's labelled speech clips of 8 s or more: WER, extra sentence ends against one block, commit delay p50/p95, stop latency p50/p95 and mean pass cost; and SHALL exit 1 when a criterion of the change fails

_Tier: bench._

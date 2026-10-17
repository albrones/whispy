## MODIFIED Requirements

### Requirement: A second engine answers when the first hears nothing
When a fallback engine is configured and the primary engine returns empty text for a prepared piece, the fallback engine SHALL transcribe the same prepared piece and its text SHALL be used. In the default pipeline the fallback engine SHALL NOT be in memory until the primary first returns nothing, and SHALL be freed after 30 seconds without a call; its model file SHALL still be checked when the pipeline is created, so a missing one fails at startup.

#### Scenario: Whisper recovers what Parakeet drops
- **WHEN** the primary engine returns nothing for a gated clip and the fallback returns « à améliorer, je pense »
- **THEN** the transcript SHALL be « à améliorer, je pense » and name the fallback engine

_Tier: unit — `whispy-core` `pipeline`._

#### Scenario: The fallback loads on demand and is freed when idle
- **WHEN** a lazy engine is created, called twice, then left without a call for longer than its idle time, then called again
- **THEN** nothing SHALL be loaded before the first call, the two calls SHALL share one load, the engine SHALL be freed after the idle time, and the next call SHALL load it again

_Tier: unit — `whispy-core` `lazy`._

### Requirement: One engine call never receives more than 20 seconds
A dictation longer than 20 s SHALL be split into pieces of at most 20 s, cut in the longest pause near the limit, covering every sample exactly once, and the piece texts SHALL be joined in order.

#### Scenario: A 65 s dictation is split
- **WHEN** 65 s of voiced audio is transcribed
- **THEN** the engine SHALL be called at least four times, never with more than 20 s, and the text SHALL hold one piece text per call in order

_Tier: unit — `whispy-core` `pipeline`, `split`._

#### Scenario: A 180 s dictation stays bounded in memory
- **WHEN** the bench transcribes a 180 s dictation in a fresh process with one engine loaded
- **THEN** its peak RSS and physical footprint SHALL be reported, and SHALL stay under 1.5 GB for Parakeet alone and for whisper alone

_Tier: bench — `v2/bench/REPORT.md`, memory table._

#### Scenario: The default pipeline stays under 1.5 GB outside a reprise
- **WHEN** the bench runs the default pipeline in a fresh process through a 180 s dictation Parakeet answers, then a ~5 s sentence Parakeet is made to miss, twice, then 32 s of quiet
- **THEN** the peak RSS and physical footprint of the dictation SHALL stay under 1.5 GB with whisper never loaded, the reprise peak and the latency the first whisper load adds SHALL be reported, and whisper SHALL be freed at the end

_Tier: bench — `v2/bench/REPORT.md`, criterion 5._

## ADDED Requirements

### Requirement: Recovery is counted on the lost clips that hold speech
The bench SHALL count recovered lost clips both over all lost clips and over the lost clips that hold speech, as classed by a reference model larger than the shipped engines (whisper large-v3-turbo, run by `v2/bench/oracle.py` outside the app) and overridden by the user's verdicts by ear. A clip SHALL count as holding speech only when the reference model decodes a confident French or English utterance that is not one of whisper's stock one-liners, or when the user heard speech in it. The reference model's output, the clip copies and the listening page SHALL stay out of the repository.

#### Scenario: Only speech clips count toward criterion 3
- **WHEN** the oracle classes one lost clip speech, one doubtful and one no speech, and an engine returns text on all three
- **THEN** the « lost speech » count SHALL be 1 of 1, and the doubtful and no-speech clips SHALL count only in « lost: text »

_Tier: unit — `banc` `oracle`._

#### Scenario: A verdict by ear overrides the oracle
- **WHEN** `bench/oracle/verdicts.tsv` marks a doubtful clip as speech
- **THEN** the bench SHALL count it as speech and show it as heard in the lost-clip table; a verdict other than speech or no-speech, or for a clip the oracle never saw, SHALL fail with the offending line

_Tier: unit — `banc` `oracle`._

#### Scenario: Nothing private is committed
- **WHEN** the oracle runs on `~/.whispy/lost/`
- **THEN** its table, clip copies and `listen.html` SHALL be written under `v2/bench/oracle/`, which is gitignored, and `REPORT.md` SHALL hold classes and counts, never the decoded text

_Tier: review — `v2/.gitignore`, `v2/bench/oracle.py`, `banc/src/report.rs`._

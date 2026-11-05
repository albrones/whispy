# v2-trial Specification

## Purpose
Decides from numbers, not from impressions, whether Whispy V2 can replace V1.
It covers what V2 records about each real dictation, the report built from it,
the comparison with V1, and the exit criteria fixed before the trial starts.

## Requirements

### Requirement: Each dictation leaves one journal line without its text
V2 SHALL append one JSON line per finished dictation to `~/.whispy/v2/dictations.jsonl` (mode 0600). The line SHALL record the time, recording duration, release-to-delivery latency, trigger (fn or socket), outcome (inserted, clipboard only, empty, heard nothing, lost, failed), engine, and text length. It SHALL NOT contain the text. A failed write SHALL be logged and SHALL NOT affect the dictation.

#### Scenario: An inserted dictation
- **WHEN** a 4 s dictation is transcribed by Parakeet to a 42-character text and pasted
- **THEN** the journal SHALL gain one line with outcome `inserted`, engine `parakeet`, length 42 and a latency in seconds

_Tier: unit — controller with a fake inserter and a temporary journal._

#### Scenario: The text never reaches the journal
- **WHEN** a dictation transcribes to « mot de passe secret »
- **THEN** no line of the journal SHALL contain « secret »

_Tier: unit._

### Requirement: banc --trial reports the trial from the journal
`banc --trial` SHALL read the journal, optionally from a given date. It SHALL print the dictation count, the number of days with at least one dictation, the count and share of each outcome, and the release-to-delivery latency p50, p95 and max over inserted dictations. It SHALL print the list of lost clips kept in `~/.whispy/v2-lost/` over the same period.

#### Scenario: Latency percentiles
- **WHEN** the journal holds 20 inserted dictations with latencies 0.1 s to 2.0 s in steps of 0.1 s
- **THEN** the report SHALL give p95 = 1.9 s and max = 2.0 s

_Tier: unit — `banc` on a fixture journal._

#### Scenario: Empty journal
- **WHEN** there is no journal file
- **THEN** the report SHALL say no dictation was recorded and exit zero

_Tier: unit._

### Requirement: The report sets V1's lost-speech rate beside V2's
`banc --trial` SHALL read `~/.whispy.log` and `~/.whispy.log.1`. V1's lines carry no date, so it SHALL use both files whole. From V1's `Transcribed a …s clip` and `Lost speech: … for a …s clip` lines, it SHALL compute V1's lost share as lost audio seconds over all transcribed and lost seconds. It SHALL compute V2's the same way from the journal, and print both. With no such V1 line, it SHALL say the comparison is unavailable.

#### Scenario: Side by side, weighted by duration
- **WHEN** V1's log holds 95 s transcribed and 5 s lost, and V2's journal 196 s inserted and 4 s lost
- **THEN** the report SHALL show V1 lost 5.0 % and V2 lost 2.0 %

#### Scenario: Pre-Parakeet logs are ignored
- **WHEN** `~/.whispy.log.presparakeet` exists
- **THEN** it SHALL NOT be read

_Tier: unit — fixture log and journal._

### Requirement: Exit criteria are written before the trial starts
`v2/TRIAL.md` SHALL define how the trial runs (V1 quit and its login item off, V2 started at login), its minimum length (3 days with dictation and 50 dictations), and the criteria V2 must all meet to replace V1:
- a lost share not above V1's;
- p95 latency of 1.5 s or less;
- `banc --labelled` WER no more than 1 point above V1's baseline, with no text on noise;
- no stuck state or restart.

It SHALL also say where the go/no-go and the list of missed V1 features are recorded.

#### Scenario: Criteria are checkable
- **WHEN** the trial ends
- **THEN** each criterion in `v2/TRIAL.md` SHALL map to a number printed by `banc --trial` or `banc --labelled`, or to a count in the V2 log

_Tier: review — the document is checked against the two reports._

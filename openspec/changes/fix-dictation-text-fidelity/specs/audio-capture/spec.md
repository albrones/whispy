## ADDED Requirements

### Requirement: An empty model result on a gated-clear clip is retried and reported

When a clip has cleared every non-speech gate — the minimum-duration guard, the near-silence RMS gate and the voiced-duration gate — it is known to carry voice. If the model nevertheless returns no text for such a clip, the system SHALL retry the call once on the **untrimmed** original clip whenever the model was given a trimmed copy, since trimming is the only transformation applied between the gates and the model call and is therefore the first suspect.

If the retry also returns no text, the system SHALL report the outcome as a **loss** at warning level, carrying the clip's duration, its peak RMS and its voiced duration, so the discarded audio is distinguishable in the log from a routine non-speech discard. The system SHALL NOT report it at the same level as clips the gates rejected: those are expected, this one is speech that vanished.

The system SHALL NOT inject placeholder text, SHALL NOT retry more than once, and SHALL NOT weaken any gate to make this case rarer — the gates are what keep invented fillers out of the user's field.

This exists because the case is common and currently invisible. Measured over one daemon log of 610 chunks, 32 clips cleared both gates, reached the model and came back empty — 180 seconds of speech, 24 of those clips longer than 3 seconds and the longest 16.7 seconds — each discarded at info level with no retry.

#### Scenario: A trimmed clip that returns nothing is retried whole

- **WHEN** a clip that passed every non-speech gate was trimmed to its voiced span and the model returns no text for the trimmed copy
- **THEN** the system SHALL call the model once more with the original untrimmed clip, and SHALL return that result if it is non-empty

_Tier: unit-mocked — `test_audio.py` (model returning `""` then text)._

#### Scenario: An untrimmed clip is not retried

- **WHEN** the model returns no text for a clip that was sent untrimmed (the span was unmeasurable, or trimming would have saved too little)
- **THEN** the system SHALL NOT call the model a second time on the same audio

_Tier: unit-mocked — `test_audio.py`._

#### Scenario: A persistent empty result is logged as a loss

- **WHEN** both the trimmed call and the untrimmed retry return no text
- **THEN** the system SHALL emit a warning identifying the clip's duration, peak RMS and voiced duration, and SHALL inject nothing

_Tier: unit-mocked — `test_audio.py` (log level and fields asserted)._

#### Scenario: A gate-rejected clip is not reported as a loss

- **WHEN** a clip is discarded by the duration guard, the RMS gate or the voiced-duration gate
- **THEN** the system SHALL keep logging that discard at its existing level and SHALL NOT call the model or emit a loss warning

_Tier: unit-mocked — `test_audio.py`._

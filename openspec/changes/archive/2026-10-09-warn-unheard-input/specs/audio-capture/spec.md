## ADDED Requirements

### Requirement: A recording that heard nothing is reported to the user
When a recording of at least `MIN_UNHEARD_ALERT_S` (0.5 s) ends with its peak level (normalized RMS x10, the waveform's scale) under `NOISE_FLOOR_PEAK_LEVEL` (0.1), the system SHALL play a failure cue distinct from the success sound and fire the input-unheard callbacks with a message naming the input device, so the UI can post a notification. Shorter recordings SHALL NOT be reported: they are accidental taps. The `capture closed` log line SHALL keep its `at the noise floor` hint for every recording under the threshold, whatever its length. The threshold SHALL carry a source comment recording its measurement: deaf recordings peaked between 0.008 and 0.055, speech reads 0.2 and above.

#### Scenario: A deaf take is reported with its device
- **WHEN** a 1 s recording on `Micro MacBook Pro` peaks at 0.055
- **THEN** the audio engine SHALL report `Micro MacBook Pro` as unheard, and the engine SHALL play the failure cue and fire the input-unheard callbacks with a message naming it

_Tier: unit-mocked — `test_audio.py` (`TestUnheardInput`), `test_engine.py` (`TestInputUnheardSurfaced`)._

#### Scenario: Speech is not reported
- **WHEN** a recording peaks at 0.2
- **THEN** no failure cue SHALL play and no input-unheard callback SHALL fire

_Tier: unit-mocked._

#### Scenario: An accidental tap is not reported
- **WHEN** a 0.1 s recording peaks at 0.0
- **THEN** nothing SHALL be reported

_Tier: unit-mocked._

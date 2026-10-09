## ADDED Requirements

### Requirement: A lost clip is kept for replay
When the model returns no text for a clip that cleared every gate (after the untrimmed retry), the system SHALL copy the clip into `~/.whispy/lost/`, SHALL name the copy in the `Lost speech` warning, and SHALL keep only the newest 20 such clips. Clips that were transcribed SHALL NOT be kept. A failure to keep the clip SHALL be logged and SHALL NOT change the transcription result.

#### Scenario: Lost clip is kept and named
- **WHEN** a clip clears every gate and the model returns empty text on both calls
- **THEN** a copy of the clip SHALL exist in the lost-clips directory and the warning SHALL contain its file name

#### Scenario: Only the newest clips are kept
- **WHEN** a clip is lost while 20 lost clips are already kept
- **THEN** the oldest kept clip SHALL be deleted and 20 clips SHALL remain

_Tier: unit — `test_audio.py`._

### Requirement: A successful transcription is logged
The system SHALL log each transcription that returns text at INFO with the clip duration and the text length, and SHALL NOT log the text itself, so successes and losses can be counted in the same log.

#### Scenario: Success line without the text
- **WHEN** the model returns « bonjour » for a 2 s clip
- **THEN** an INFO line SHALL report a transcribed 2.00 s clip and SHALL NOT contain « bonjour »

_Tier: unit — `test_audio.py`._

### Requirement: Quiet speech gets a louder last try
When the model returns no text for a clip that cleared every gate, after the untrimmed retry, the system SHALL make one last call on a copy of the original with its DC offset removed and scaled to a whole-clip RMS of 0.05, unless the clip is already at least that loud. The copy SHALL be deleted after the call.

#### Scenario: Quiet dictation is recovered
- **WHEN** a clip at RMS 0.012 comes back empty from the trimmed and the untrimmed calls
- **THEN** the system SHALL call the model a third time on a copy at RMS 0.05 and SHALL return its text

_Tier: unit — `test_audio.py`; measured on 20 real lost clips in design.md._

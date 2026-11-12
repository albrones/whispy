## ADDED Requirements

### Requirement: Type while speaking in toggle mode
When the trigger mode is toggle and `type_while_speaking` is on in V1's config file (V1's default: on), V2 SHALL cut the recording at pauses while it records, transcribe each piece as soon as it is cut, and type it into the frontmost app in recording order. The stopping press SHALL transcribe and type the last piece. The pieces joined end to end SHALL be the dictation, with no piece typed twice and none dropped. In hold mode, or with the setting off, the whole dictation SHALL be inserted once at the end, as before. The menu SHALL show V1's « Type while speaking » row under SETTINGS, with V1's trailing ✓ when on, and toggling it SHALL save only that key and apply to the next dictation.

#### Scenario: First sentence typed before the stop
- **WHEN** the user, in toggle mode with the setting on, says two sentences separated by a one-second pause
- **THEN** the first sentence SHALL be typed before the stopping press, and the second after it

#### Scenario: Hold mode unchanged
- **WHEN** the user holds the trigger and dictates two sentences with a pause
- **THEN** nothing SHALL be typed until the release, then the whole text SHALL be inserted once

#### Scenario: The menu row follows the setting
- **WHEN** the user unticks « Type while speaking »
- **THEN** `type_while_speaking` SHALL be false in config.json, every other key unchanged, and the next toggle dictation SHALL be inserted once at the end

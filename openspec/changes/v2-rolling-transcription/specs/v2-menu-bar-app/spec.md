## MODIFIED Requirements

### Requirement: Type while speaking in toggle mode
When the trigger mode is toggle and `type_while_speaking` is on in V1's config file (V1's default: on), V2 SHALL re-transcribe the sentence in progress while it records and type each sentence into the frontmost app once it is committed (see `v2-transcription-core`, « A dictation typed while spoken is committed sentence by sentence »), in recording order. The stopping press SHALL transcribe the open sentence with the full default pipeline and type it. Nothing typed SHALL ever be erased or retyped, no text SHALL be typed twice, and none SHALL be dropped. In hold mode, or with the setting off, the whole dictation SHALL be inserted once at the end, as before. The menu SHALL show V1's « Type while speaking » row under SETTINGS, with V1's trailing ✓ when on, and toggling it SHALL save only that key and apply to the next dictation.

#### Scenario: First sentence typed before the stop
- **WHEN** the user, in toggle mode with the setting on, says two sentences, the second starting right after the first
- **THEN** the first sentence SHALL be typed before the stopping press, and the second after it

_Tier: bench — `banc --streaming`; manual — TextEdit._

#### Scenario: A thinking pause is not a sentence end
- **WHEN** the user pauses 1 s in the middle of a sentence, then finishes it
- **THEN** the sentence SHALL be typed once, as the model punctuates it with its continuation, not cut at the pause

_Tier: bench — `banc --streaming`, extra sentence ends._

#### Scenario: Hold mode unchanged
- **WHEN** the user holds the trigger and dictates two sentences with a pause
- **THEN** nothing SHALL be typed until the release, then the whole text SHALL be inserted once

#### Scenario: The menu row follows the setting
- **WHEN** the user unticks « Type while speaking »
- **THEN** `type_while_speaking` SHALL be false in config.json, every other key unchanged, and the next toggle dictation SHALL be inserted once at the end

## ADDED Requirements

### Requirement: The pill shows the words as they are heard
While a dictation is typed while spoken, V2's pill SHALL show the latest words heard as one line of text beside its bars: committed words in white (0.95 alpha), words not yet committed in white at 0.5 alpha. On the first non-empty caption the pill SHALL widen from 168 to 560 pt, stay bottom-centre and keep that width until the recording ends; a text longer than the line SHALL be truncated at its head, so the latest words stay visible. The caption SHALL be cleared when a recording starts and SHALL never be shown in hold mode or with the setting off. The pill SHALL still ignore the mouse and never take focus. The pure parts (widths, text rectangle, bar placement in the wide pill) SHALL be unit-tested.

#### Scenario: Words appear before they are typed
- **WHEN** the user dictates in toggle mode with the setting on
- **THEN** the words SHALL appear in the pill, faded, within about a second of being said, and turn white when their sentence is typed

_Tier: manual._

#### Scenario: Hold mode keeps V1's pill
- **WHEN** the user dictates in hold mode
- **THEN** the pill SHALL stay 168 pt wide with no text

_Tier: unit — controller with a recording feedback._

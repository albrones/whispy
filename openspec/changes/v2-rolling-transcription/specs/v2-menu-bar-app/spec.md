## MODIFIED Requirements

### Requirement: Type while speaking in toggle mode
When the trigger mode is toggle and `type_while_speaking` is on in V1's config file (V1's default: on), V2 SHALL re-transcribe the dictation's last seconds while it records and type each committed passage into the frontmost app (see `v2-transcription-core`, « A dictation typed while spoken is committed word by word, in context »), in recording order. The stopping press SHALL transcribe what is not typed yet, in its context, and type it. Nothing typed SHALL ever be erased or retyped, no text SHALL be typed twice, and none SHALL be dropped. In hold mode, or with the setting off, the whole dictation SHALL be inserted once at the end, as before. The menu SHALL show V1's « Type while speaking » row under SETTINGS, with V1's trailing ✓ when on, and toggling it SHALL save only that key and apply to the next dictation.

#### Scenario: First sentence typed before the stop
- **WHEN** the user, in toggle mode with the setting on, says two sentences and keeps talking
- **THEN** the first sentence SHALL be typed before the stopping press, and what was not typed yet after it

_Tier: bench — `banc --streaming`; manual — TextEdit._

#### Scenario: A thinking pause is not a sentence end
- **WHEN** the user pauses 1 s in the middle of a sentence, then finishes it
- **THEN** the sentence SHALL be typed once, punctuated as the model hears it with its continuation, never with a period at the pause

_Tier: bench — `banc --streaming`, extra sentence ends._

#### Scenario: Hold mode unchanged
- **WHEN** the user holds the trigger and dictates two sentences with a pause
- **THEN** nothing SHALL be typed until the release, then the whole text SHALL be inserted once

#### Scenario: The menu row follows the setting
- **WHEN** the user unticks « Type while speaking »
- **THEN** `type_while_speaking` SHALL be false in config.json, every other key unchanged, and the next toggle dictation SHALL be inserted once at the end

## ADDED Requirements

### Requirement: The pill shows the words as they are heard
In every dictation (hold mode, toggle mode with « Type while speaking » on or off), V2 SHALL re-transcribe the recording as it is spoken and its pill SHALL show the latest words heard as one line of text centred under its bars: words two passes agree on in white (0.95 alpha), the others in white at 0.5 alpha. On the first non-empty caption the pill SHALL grow from 168 to 560 pt wide and by one text row downward, its bars staying where they were on screen and centred, and keep that size until the recording ends; a text longer than the line SHALL be truncated at its head, so the latest words stay visible. The caption SHALL be cleared when a recording starts. Only « Type while speaking » types text live: in hold mode or with the setting off, the inserted text SHALL be the whole dictation transcribed once at the stop, as before. The pill SHALL still ignore the mouse and never take focus. The pure parts (panel frame, bar placement, text rectangle) SHALL be unit-tested.

#### Scenario: Words appear before they are typed
- **WHEN** the user dictates in toggle mode with the setting on
- **THEN** the words SHALL appear in the pill, faded, within about a second of being said, and turn white when they are typed

_Tier: manual._

#### Scenario: Hold mode shows the words and types nothing live
- **WHEN** the user dictates in hold mode, or in toggle mode with the setting off
- **THEN** the pill SHALL show the words while recording, nothing SHALL be typed before the stop, and the whole dictation SHALL be inserted once at the stop

_Tier: unit — controller with a recording feedback._

#### Scenario: The waveform stays centred
- **WHEN** the first words of a dictation appear
- **THEN** the bars SHALL keep their place on screen and the text SHALL sit centred under them

_Tier: unit — `pill_geometry`; manual — the look._

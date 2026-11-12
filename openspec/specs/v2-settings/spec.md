# v2-settings Specification

## Purpose
Lets the Rust app use V1's settings: the same file, the same keys and the same
defaults. The user's choices then carry over in both directions, from V1 to the
Rust app and back.

## Requirements

### Requirement: V2 reads V1's config file
V2 SHALL read `~/.config/whispy/config.json` at startup and SHALL take three keys from it, `copy_to_clipboard`, `trigger_mode` and `trigger`, with V1's defaults (`true`, `"hold"`, `null` meaning Fn). A missing file, unparseable JSON, or a value of the wrong type or outside V1's accepted values SHALL fall back to that key's default without failing the start, and SHALL be logged.

#### Scenario: V1's choices are picked up
- **WHEN** the file holds `{"trigger_mode": "toggle", "trigger": 61, "copy_to_clipboard": true}`
- **THEN** V2 SHALL start in toggle mode on Right Option, delivering through the clipboard

_Tier: unit — settings parser on a temporary file._

#### Scenario: A broken file does not stop the app
- **WHEN** the file holds `{"trigger_mode": "sometimes"`
- **THEN** V2 SHALL start with `hold`, Fn and clipboard delivery, and log that the file could not be used

_Tier: unit._

### Requirement: A menu change is saved without losing other keys
When the user changes a setting from the menu, V2 SHALL re-read the file and set only the changed key. It SHALL write the file atomically, through a temporary file renamed over it, with mode 0600 in a 0700 directory. Every other key and value in the file SHALL be kept unchanged, including keys V2 does not know. When the file is unreadable at save time, V2 SHALL NOT overwrite it, and SHALL log and say so.

#### Scenario: V1-only keys survive
- **WHEN** the file holds `max_chunk_s`, `vocabulary` and `start_at_login` and the user turns on Toggle mode in V2
- **THEN** the file SHALL hold `trigger_mode: "toggle"` and the three other keys with their exact previous values

_Tier: unit._

#### Scenario: An unreadable file is not replaced
- **WHEN** the file holds invalid JSON and the user turns off Copy to clipboard
- **THEN** the file SHALL be left byte-for-byte unchanged and the menu SHALL say the setting could not be saved

_Tier: unit._

### Requirement: Settings apply without a restart
A change made from the menu SHALL take effect for the next dictation. A trigger change SHALL make V2 listen to the new key and stop answering the old one, with no restart. A change made while a dictation is under way SHALL NOT alter that dictation.

#### Scenario: Switching to Right Option
- **WHEN** the user picks Right Option in the Trigger submenu
- **THEN** the next Right Option press SHALL start a dictation and an Fn press SHALL do nothing

_Tier: unit — trigger decoding; manual — real keys._

### Requirement: Copy to clipboard off types the text
With `copy_to_clipboard` true, V2 SHALL deliver as it does today: clipboard, ⌘V, then the clipboard restored. With it false, V2 SHALL type the text through System Events `keystroke`, passing the text as data and never as script source, and SHALL leave the clipboard untouched, as V1 does.

#### Scenario: Typed delivery keeps the clipboard
- **WHEN** `copy_to_clipboard` is false and « bonjour » is delivered
- **THEN** the inserter SHALL type « bonjour » and the clipboard SHALL hold what it held before

_Tier: unit — inserter command built with a fake runner; manual — real typing._

#### Scenario: Quotes cannot break out of the script
- **WHEN** the text to type is `" & do shell script "touch /tmp/x`
- **THEN** that text SHALL be typed literally and no command SHALL run

_Tier: unit._

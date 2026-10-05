## ADDED Requirements

### Requirement: Injected text is independent of the keyboard layout

Text delivered to the focused application SHALL be byte-identical to the cleaned transcript regardless of the keyboard layout active on the user's machine. The default delivery path SHALL therefore be the one that hands the text over as data (clipboard paste) rather than the one that resolves each character to a key position.

Synthetic-keystroke delivery SHALL remain available as an explicit opt-out and SHALL be documented as correct only on a US layout. It is not layout-safe and SHALL NOT be presented as if it were: on a French AZERTY layout, measured on a 178-second dictation, every `,` the model emitted arrived as `.`, and `â` arrived as `q` — the US key position for `a`. Characters that have a direct key on the active layout (`é`, `à`, `è`, `ç`) survive; dead-key characters and punctuation do not, so the corruption is silent and partial rather than obviously broken.

The system SHALL NOT attempt to repair layout corruption after the fact by rewriting text, and SHALL NOT maintain a per-layout character mapping: both would have to track every layout the OS supports.

#### Scenario: Accented and punctuated dictation arrives intact by default

- **WHEN** a transcript containing `,`, `â`, `ê` and `ô` is injected on a machine whose active keyboard layout is not US
- **THEN** the focused field SHALL receive those characters exactly, with no substitution

#### Scenario: Clipboard paste is the default delivery path

- **WHEN** the application starts with no saved configuration and a transcription completes
- **THEN** the text SHALL be delivered through the clipboard-paste path, not through synthetic keystrokes

#### Scenario: Keystroke mode remains reachable

- **WHEN** the user sets `copy_to_clipboard` to false
- **THEN** the injector SHALL use the synthetic-keystroke path exactly as it does today

_Tier: unit-pure for the mode selection (`test_injection.py`); the layout behaviour itself is platform-real and belongs to the per-OS smoke tier — a CI runner has one layout._

#### Scenario: Keystroke mode's limitation is documented

- **WHEN** the configuration reference describes `copy_to_clipboard`
- **THEN** it SHALL state that disabling it types the transcript key by key and that the result is only correct on a US keyboard layout

_Tier: unit-pure — `test_website.py` / docs check._

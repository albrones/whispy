## ADDED Requirements

### Requirement: A floating indicator shows recording and transcribing
While V2 records, a small panel SHALL show that it is recording, with a live input level. While it transcribes, the panel SHALL show that. The panel SHALL never take keyboard focus or activate V2. It SHALL appear above every Space, including full-screen apps, and SHALL hide when V2 returns to idle.

#### Scenario: Focus stays in the user's app
- **WHEN** a dictation starts while a text field in another app has focus
- **THEN** the panel SHALL appear and that text field SHALL keep the keyboard focus

_Tier: manual — and unit for the show/hide sequence driven by machine states._

#### Scenario: The panel follows the state
- **WHEN** the machine goes recording → transcribing → inserting → idle
- **THEN** the panel SHALL show recording, then transcribing, then hide

_Tier: unit — controller with a fake indicator._

### Requirement: A dictation that heard nothing is reported
A dictation of 0.5 s or more whose level stays under V1's noise floor SHALL insert nothing and call no engine. The level is the RMS of a 30 ms window times ten, V1's scale, and the floor is 0.1: no window louder than RMS 0.01. It SHALL play the system failure sound and put « Microphone heard nothing » with the input device's name in the menu as the last problem. It SHALL NOT be kept as lost speech.

#### Scenario: A deaf take
- **WHEN** a 3 s dictation's windows never exceed RMS 0.006 on the device « MacBook Pro Microphone »
- **THEN** no engine SHALL be called, nothing SHALL be inserted, and the menu SHALL show « Microphone heard nothing (MacBook Pro Microphone) »

_Tier: unit — controller with a fake capture._

#### Scenario: Quiet speech is not a deaf take
- **WHEN** a 3 s dictation's samples never exceed 0.05 but its windows reach RMS 0.05
- **THEN** it SHALL be transcribed as usual

_Tier: unit._

#### Scenario: A short tap is not a deaf take
- **WHEN** a dictation lasts 0.3 s with no sound
- **THEN** nothing SHALL be reported

_Tier: unit._

### Requirement: Each dictation uses the current default input device
Each dictation SHALL open the system default input device at the moment it starts, so a device change in System Settings applies to the next dictation without a restart.

#### Scenario: Switching to a headset
- **WHEN** the default input changes from the built-in microphone to a headset between two dictations
- **THEN** the second dictation SHALL record from the headset

_Tier: manual._

### Requirement: V2 writes a rotated log file without dictated text
V2 SHALL write its status lines, errors and one line per dictation to `~/.whispy/v2/whispy2.log`, with mode 0600. When the file exceeds 5 MB, it SHALL be renamed to `whispy2.log.1`, replacing the previous copy, and a new file SHALL be started. No log line SHALL contain dictated text.

#### Scenario: Rotation
- **WHEN** a write would take the log over 5 MB
- **THEN** the log SHALL become `whispy2.log.1` and the line SHALL go to a new `whispy2.log`

_Tier: unit — logger on a temporary directory with a small limit._

#### Scenario: Launched from Finder
- **WHEN** V2 is launched as an installed bundle with no terminal
- **THEN** its status lines SHALL be in `~/.whispy/v2/whispy2.log`

_Tier: manual._

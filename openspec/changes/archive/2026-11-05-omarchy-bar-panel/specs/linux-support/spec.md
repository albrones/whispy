## ADDED Requirements

### Requirement: Omarchy dictation key presets
`omarchy-dictation-whispy trigger <preset>` SHALL accept exactly the `omarchy_trigger` presets (`right_option_hold`, `right_ctrl_hold`, `f9_hold`, `left_option_space_toggle`), save the preset through `POST /config`, write `~/.config/whispy/shortcuts.lua` binding only the chosen key, and reload Hyprland. Hold presets SHALL be non-consuming.

#### Scenario: A preset is chosen
- **WHEN** `trigger right_ctrl_hold` runs with Whispy answering
- **THEN** the config SHALL hold `omarchy_trigger: right_ctrl_hold`, the file SHALL bind Right Ctrl push-to-talk and no other preset key, and `hyprctl reload` SHALL run

_Tier: unit-mocked — `tests/test_omarchy_adapter.py` (stand-in API, fake `hyprctl`); live — `hyprctl binds` on the Omarchy VM._

#### Scenario: Unknown preset or Whispy down
- **WHEN** the preset is unknown, or nothing answers on the API port
- **THEN** the script SHALL exit non-zero and leave the binding file and Hyprland untouched

_Tier: unit-mocked — `tests/test_omarchy_adapter.py`._

#### Scenario: The chosen key dictates
- **WHEN** Right Ctrl is chosen in the panel and held, then Right Option is held
- **THEN** Right Ctrl SHALL dictate and Right Option SHALL NOT, also after logging in again

_Tier: manual-ui — Omarchy VM._

### Requirement: Omarchy bar widget
On Omarchy, the installer SHALL link a bar widget (`whispy.panel`) and place it in the right section of the bar. Its icon SHALL show Whispy's state with the macOS braille waveform; a click SHALL open a panel with the dictation key, model and language (information only), Copy to clipboard, Start at login, the last dictation, and a way to start Whispy when it is stopped. Settings SHALL apply without a restart. At rest the widget SHALL read `/status` at most every 30 s.

#### Scenario: State logic
- **WHEN** the API is unreachable, recording, transcribing (or the backend says `/stop` is running), loading, or idle
- **THEN** the widget state SHALL be stopped, recording, transcribing, loading, or ready respectively

_Tier: unit-pure — `tests/test_omarchy_panel_model.py` (node)._

#### Scenario: Whispy stopped
- **WHEN** the daemon is stopped and the panel is opened
- **THEN** the icon SHALL be greyed, the panel SHALL read « Whispy stopped » and offer « Start Whispy »

_Tier: manual-ui — Omarchy VM._

#### Scenario: A dictation drives the icon
- **WHEN** the dictation key is held, then released
- **THEN** the icon SHALL show listening, then transcribing, then ready

_Tier: manual-ui — Omarchy VM._

### Requirement: Omarchy recording pill
While recording, the bar widget SHALL show a pill at the bottom centre of the focused monitor: a layer-shell overlay with no keyboard interactivity and an empty input region, so the focused window keeps the focus. Its bars SHALL follow `GET /level`, polled only while recording, and SHALL stay flat at or below the transcription silence gate.

#### Scenario: Flat in silence, moving with speech
- **WHEN** the level is at or below 0.05, or above it
- **THEN** the bars SHALL be at their minimum height, or grow with the level, taller in the middle

_Tier: unit-pure — `tests/test_omarchy_panel_model.py` (node)._

#### Scenario: Focus is kept
- **WHEN** a dictation runs into a focused window
- **THEN** the pill SHALL appear and the text SHALL land in that window, which stays focused

_Tier: manual-ui — Omarchy VM._

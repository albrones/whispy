## ADDED Requirements

### Requirement: Pure visualization computation
The audio-level value and the menu-bar animation frame SHALL be produced by pure, unit-tested functions independent of `sounddevice` and `rumps`. The audio-level function SHALL map a raw RMS sample to a smoothed 0.0–1.0 level (normalize, clamp to 1.0, then apply exponential moving average against the previous level). The frame-selection function SHALL return the scrolling waveform frame for the current index when active and the idle frame when inactive. The UI callbacks SHALL delegate to these functions.

#### Scenario: RMS maps to clamped normalized level
- **WHEN** `rms_to_level` receives an RMS value whose normalized form exceeds 1.0
- **THEN** it SHALL clamp the contribution to 1.0 before smoothing

_Tier: unit-pure._

#### Scenario: Exponential moving average applied
- **WHEN** `rms_to_level` is called with a previous smoothed level and a smoothing factor
- **THEN** it SHALL return `smoothing * prev + (1 - smoothing) * normalized`

_Tier: unit-pure._

#### Scenario: Active animation cycles frames
- **WHEN** `select_frame` is called with `is_active` true for increasing frame indices
- **THEN** it SHALL return successive waveform frames, wrapping modulo the frame count

_Tier: unit-pure._

#### Scenario: Idle shows the idle frame
- **WHEN** `select_frame` is called with `is_active` false
- **THEN** it SHALL return the idle frame regardless of index

_Tier: unit-pure._

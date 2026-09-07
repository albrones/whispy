## ADDED Requirements

### Requirement: Toggle mode setting

The menu SHALL expose a **Toggle mode** setting as a checked item in the Settings
section, alongside the existing `Copy to clipboard` toggle. It SHALL reflect the
persisted `trigger_mode` value, SHALL persist the change through the engine's
config update when selected, and SHALL apply without requiring a manual Restart.
It SHALL be a setting independent of the Trigger submenu, so that any trigger can
be combined with either mode without duplicating the trigger list.

#### Scenario: Toggle mode reflects configuration

- **WHEN** the menu is built
- **THEN** the Toggle mode item SHALL show as checked exactly when `trigger_mode` is `"toggle"`

#### Scenario: Toggling persists and applies

- **WHEN** the user selects the Toggle mode item
- **THEN** `trigger_mode` SHALL be persisted through the engine's config update, the item's check state SHALL update, and the new mode SHALL apply without a manual Restart

#### Scenario: Toggle mode participates in theming

- **WHEN** the system appearance flips (light/dark)
- **THEN** the Toggle mode item's title SHALL be rebuilt with the correct accent and check state, like the other settings items

#### Scenario: Mode is independent of trigger choice

- **WHEN** the user changes the trigger while Toggle mode is enabled
- **THEN** the mode SHALL remain enabled, and the Trigger submenu SHALL NOT gain per-mode duplicate entries

## MODIFIED Requirements

### Requirement: Trigger selection submenu

The menu bar SHALL provide a **Trigger** submenu listing a curated set of trigger
keys, replacing the static "Hold Fn to dictate" label. The submenu SHALL present
each preset as a selectable item and SHALL show a checkmark on the item matching
the active trigger. The submenu title SHALL reflect the active trigger (e.g.
"Trigger: Fn").

The curated set SHALL contain the inert single keys (Fn, Right Command, Right
Option, F13) **and** modifier-combination presets drawn from the
`Control+Option+Command` tier. Only triggers that are inert on their own SHALL be
offered: the event tap is listen-only and cannot consume the event, so a trigger
that the focused application also binds would fire that application's shortcut on
every start and stop, and a shortcut that opens a focused panel would redirect the
subsequent injection into it.

Combination presets SHALL be labelled by their key combination, and SHALL NOT be
labelled with a language or any other semantic the system does not actually apply.

The submenu SHALL remain single-selection: exactly one trigger is active at a
time, and the submenu SHALL NOT offer arbitrary key capture.

#### Scenario: Submenu lists curated presets

- **WHEN** the menu bar is built
- **THEN** the Trigger submenu SHALL contain one item per curated preset, covering both the inert single keys and the combination presets, and SHALL NOT offer arbitrary key capture

#### Scenario: Active trigger is checked

- **WHEN** the menu is displayed and a trigger is configured (or the default applies)
- **THEN** exactly the item matching the active trigger SHALL show a checkmark, and the submenu title SHALL name that trigger

#### Scenario: Default selection is Fn

- **WHEN** no `trigger` override is configured
- **THEN** the Fn preset SHALL be shown as the active (checked) trigger

#### Scenario: Combination preset is selectable and labelled by its keys

- **WHEN** the user selects a combination preset
- **THEN** it SHALL become the active trigger, the submenu title SHALL show the key combination, and the label SHALL name the keys rather than a language

#### Scenario: A hand-edited combination renders as itself

- **WHEN** the configured trigger is a combination string that matches no preset
- **THEN** the submenu title SHALL display that combination string rather than resolving it through the single-keycode name table

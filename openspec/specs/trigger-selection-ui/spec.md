# trigger-selection-ui Specification

## Purpose
TBD - created by archiving change configurable-trigger-key. Update Purpose after archive.

## Requirements

### Requirement: Selecting a trigger persists and applies the choice
Selecting a Trigger submenu item SHALL persist the chosen key to the `trigger` config key and apply it without requiring a manual Restart. The submenu title and checkmark SHALL update to the new selection.

#### Scenario: User picks a new trigger
- **WHEN** the user selects a non-active item in the Trigger submenu
- **THEN** the choice SHALL be saved to config via the engine's config update, the checkmark SHALL move to the selected item, and the title SHALL update to the new trigger

#### Scenario: Selection takes effect immediately
- **WHEN** the user selects a new trigger while the app is running
- **THEN** the new key SHALL become the active push-to-talk trigger without a manual Restart

### Requirement: Trigger submenu participates in theming
The Trigger submenu items SHALL re-render their accented/checked titles when the system appearance changes, like the other settings submenus.

#### Scenario: Appearance flip rebuilds trigger titles
- **WHEN** the system appearance flips (light/dark)
- **THEN** the Trigger submenu item titles SHALL be rebuilt with the correct accent and check state for the active trigger

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

### Requirement: Trigger preset submenu

The menu bar SHALL provide a **Trigger** submenu listing a curated set of trigger
keys, replacing the static "Hold Fn to dictate" label. The submenu SHALL present
each preset as a selectable item and SHALL show a checkmark on the item matching
the active trigger. The submenu title SHALL reflect the active trigger (e.g.
"Trigger: Fn").

The curated set SHALL contain only inert single keys: Fn, Right Command, Right
Option, F13. It SHALL NOT offer modifier-combination presets. Only triggers that
are inert on their own SHALL be offered: the event tap is listen-only and cannot
consume the event, so a trigger that the focused application also binds would
fire that application's shortcut on every start and stop.

The submenu SHALL remain single-selection: exactly one trigger is active at a
time, and the submenu SHALL NOT offer arbitrary key capture.

A modifier-combination trigger written by hand into the config file SHALL still
be honoured by the listener and SHALL be displayed as itself in the submenu
title; it simply has no preset item.

#### Scenario: Submenu lists curated presets

- **WHEN** the menu bar is built
- **THEN** the Trigger submenu SHALL contain exactly one item per inert single-key preset (Fn, Right Command, Right Option, F13), SHALL contain no modifier-combination item, and SHALL NOT offer arbitrary key capture

#### Scenario: Active trigger is checked

- **WHEN** the menu is displayed and a trigger is configured (or the default applies)
- **THEN** exactly the item matching the active trigger SHALL show a checkmark, and the submenu title SHALL name that trigger

#### Scenario: Default selection is Fn

- **WHEN** no `trigger` override is configured
- **THEN** the Fn preset SHALL be shown as the active (checked) trigger

#### Scenario: A hand-edited combination renders as itself

- **WHEN** the configured trigger is a combination string that matches no preset
- **THEN** the submenu title SHALL display that combination string rather than resolving it through the single-keycode name table, and no preset item SHALL be checked

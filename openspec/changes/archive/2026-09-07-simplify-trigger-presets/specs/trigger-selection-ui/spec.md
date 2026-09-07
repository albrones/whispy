## REMOVED Requirements

### Requirement: Trigger selection submenu
**Reason**: The curated set no longer offers modifier-combination presets, so the requirement's "Combination preset is selectable and labelled by its keys" scenario describes a menu item that does not exist. The requirement is re-stated under `Trigger preset submenu` with single keys only.
**Migration**: Nothing for users: a persisted `"trigger": "ctrl+alt+cmd+<key>"` string stays valid and is still honoured by the listener; it just has no preset item to check.

## ADDED Requirements

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

## ADDED Requirements

### Requirement: Trigger selection submenu
The menu bar SHALL provide a **Trigger** submenu listing a curated set of push-to-talk keys, replacing the static "Hold Fn to dictate" label. The submenu SHALL present each preset as a selectable item and SHALL show a checkmark on the item matching the active trigger. The submenu title SHALL reflect the active trigger (e.g. "Trigger: Fn"), consistent with the Model and Language submenus.

#### Scenario: Submenu lists curated presets
- **WHEN** the menu bar is built
- **THEN** the Trigger submenu SHALL contain one item per curated preset (Fn, Right Command, Right Option, F13, Caps Lock) and SHALL NOT offer arbitrary key capture

#### Scenario: Active trigger is checked
- **WHEN** the menu is displayed and a trigger is configured (or the default applies)
- **THEN** exactly the item matching the active trigger SHALL show a checkmark, and the submenu title SHALL name that trigger

#### Scenario: Default selection is Fn
- **WHEN** no `trigger` override is configured
- **THEN** the Fn preset SHALL be shown as the active (checked) trigger

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

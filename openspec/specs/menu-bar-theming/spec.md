# menu-bar-theming Specification

## Purpose
Brand-accent styling of the macOS menu-bar dropdown — a brand-green status dot, an uppercase letter-spaced "SETTINGS" header, and brand-green checkmarks — rendered via `NSMenuItem` attributed titles so the app's menu matches the promotional website. The accent color is appearance-aware (brighter green on dark menus, dimmer on light), and all native menu behavior (hover, click-to-dismiss, submenu positioning, keyboard navigation) is unchanged. macOS-only: the Linux tray (pystray) renders plain text labels and has no styling equivalent.

## Requirements

### Requirement: Brand-accent status dot

The macOS menu-bar status line SHALL be prefixed with a brand-green "●" glyph rendered via an attributed title, mirroring the website's status dot. The glyph SHALL appear regardless of the status text (Ready, Recording, Loading, etc.).

#### Scenario: Status line shows accent dot

- **WHEN** the menu is opened on macOS
- **THEN** the status row displays a brand-green "●" immediately before the status text

#### Scenario: Dot persists across status changes

- **WHEN** the engine status changes (e.g. Ready → Recording → Transcribing)
- **THEN** the updated status text retains the brand-green "●" prefix

### Requirement: Brand-accent section header

The "Settings" section header SHALL be rendered in brand-green, uppercase ("SETTINGS"), with letter-spacing, via an attributed title, mirroring the website's section label. It SHALL remain a non-interactive (disabled) menu item.

#### Scenario: Settings header styled

- **WHEN** the menu is opened on macOS
- **THEN** the section header reads "SETTINGS" in brand-green with letter-spacing and is not clickable

### Requirement: Brand-accent checkmarks

Selected items in the Model and Language submenus, and the "Copy to clipboard" toggle when enabled, SHALL indicate selection with a brand-green checkmark glyph rendered via attributed title, in place of the native checkmark state. At most one item per submenu SHALL show the checkmark, reflecting the current configuration.

#### Scenario: Selected model shows accent checkmark

- **WHEN** the Model submenu is opened
- **THEN** the currently configured model shows a brand-green checkmark and no other model does

#### Scenario: Selecting a new item moves the checkmark

- **WHEN** the user selects a different model or language
- **THEN** the brand-green checkmark moves to the newly selected item and is removed from the previous one, and the change is persisted

#### Scenario: Copy toggle reflects state

- **WHEN** "Copy to clipboard" is enabled
- **THEN** it shows a brand-green checkmark; **WHEN** disabled, it shows none

### Requirement: Appearance-aware accent color

The brand-accent color used in the menu SHALL adapt to the system appearance: the brighter brand green on dark menus and the dimmer brand green on light menus, so accent text and glyphs remain legible in both appearances. The menu's base text, background, and the macOS system accent color SHALL continue to be handled by the native menu.

#### Scenario: Dark appearance

- **WHEN** the system is in dark appearance
- **THEN** the menu accents use the brighter brand green

#### Scenario: Light appearance

- **WHEN** the system is in light appearance
- **THEN** the menu accents use the dimmer brand green

#### Scenario: Native styling preserved

- **WHEN** the menu is displayed in either appearance
- **THEN** non-accent text, the menu background, hover highlight, click-to-dismiss, submenu positioning, and keyboard navigation behave exactly as a native menu

### Requirement: Linux tray unaffected

The Linux tray (pystray) SHALL retain its existing plain text labels and SHALL NOT attempt brand-accent attributed styling, which pystray does not support. Menu-bar theming is a macOS-only capability.

#### Scenario: Linux tray renders plain labels

- **WHEN** the app runs on Linux
- **THEN** the tray menu uses plain text labels with no attributed-title styling and no errors are raised

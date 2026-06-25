## Why

The promotional website shows a polished menu-bar dropdown — brand-green status dot, an uppercase "SETTINGS" section header, and brand-green checkmarks — that adapts to the system appearance. The real app menu (`src/whispy/ui/menu_bar.py`, rumps → native `NSMenu`) renders plain system-styled rows with none of this brand identity. Users who see the site then open the app find the two don't match. Bringing the app's accent styling closer to the website strengthens brand consistency at zero cost to native menu behavior.

## What Changes

- Style the macOS menu-bar dropdown rows with the brand accent via `NSMenuItem.setAttributedTitle_`:
  - Brand-green "●" glyph on the status line (mirrors the website's glowing status dot).
  - Brand-green, uppercase, letter-spaced "SETTINGS" section header.
  - Brand-green checkmarks on selected Model / Language items and the "Copy to clipboard" toggle (replacing the native checkmark glyph).
- Make the accent appearance-aware: use the brighter brand green on dark menus and the dimmer variant on light menus so contrast holds in both system appearances. Light/dark and the macOS system accent color continue to be handled natively.
- Keep all native menu behavior unchanged — hover highlight, click-to-dismiss, submenu positioning, keyboard navigation. No custom `NSView` rows.
- Linux (`src/whispy/platform/linux/tray.py`, pystray) is **out of scope** for styling — pystray menus are text-label only and cannot render attributed titles or custom colors. Linux keeps its existing plain labels. Documented as a known platform limitation.

## Capabilities

### New Capabilities
- `menu-bar-theming`: Brand-accent styling of the macOS menu-bar dropdown (status dot, section header, checkmarks) using attributed titles, with appearance-aware accent color and no change to native menu behavior.

### Modified Capabilities
<!-- None — the menu bar has no existing spec; this introduces one. -->

## Impact

- **Code**: `src/whispy/ui/menu_bar.py` (row construction + a small attributed-title helper). Possibly a new `src/whispy/ui/menu_theme.py` for the accent/color logic.
- **Platforms**: macOS only. Linux tray unchanged (documented limitation).
- **Dependencies**: None new — uses existing pyobjc/`AppKit` (`NSAttributedString`, `NSColor`) already pulled in via rumps.
- **Behavior/risk**: Low. Attributed titles are cosmetic; native menu interaction and existing callbacks are untouched. No new permissions.

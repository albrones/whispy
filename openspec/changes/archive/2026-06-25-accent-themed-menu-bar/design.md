## Context

The macOS menu lives in `src/whispy/ui/menu_bar.py` as `WhisperMenuBarApp(rumps.App)`. rumps wraps each row in a native `NSMenuItem`, exposed as `item._menuitem` (already used at `menu_bar.py:209` for the permission item's `setHidden_`). The website's menu mockup (`website/index.html` `.demo-dropdown`, styled in `website/styles.css:232+`) uses brand green `--green: #24bf9e` / `--green-dim: #1c9a7f` for a status dot, an uppercase letter-spaced "SETTINGS" header, and green checkmarks.

Verified on this machine (rumps 0.4.0, pyobjc present): `NSMenuItem.setAttributedTitle_`, `NSMenuItem.setView_`, and `NSColor.controlAccentColor` are all available. This means we can recolor row text/glyphs without replacing the native menu.

## Goals / Non-Goals

**Goals:**
- Bring the macOS menu's accent identity in line with the website: green status dot, green uppercase section header, green checkmarks.
- Keep the accent legible in both light and dark system appearances.
- Preserve 100% of native menu behavior (hover, dismiss, submenu, keyboard).

**Non-Goals:**
- Reproducing the website's floating glass card (rounded corners, blur). The native menu container is not stylable; not pursued.
- The green background "pill" on the active language row — needs custom `NSView` rows that break native behavior; out of scope.
- Linux tray styling — pystray menus are text-only.

## Decisions

### Decision: Attributed titles, not custom NSViews

Use `NSMenuItem.setAttributedTitle_` with `NSAttributedString` to color text and glyphs. Each accent row becomes an attributed string with the brand color applied to the relevant range (whole title, or a leading glyph).

- **Why over `setView_`**: Custom `NSView` rows give pixel control (the glass pill) but lose automatic highlight tracking, click forwarding, and dismiss — all of which would have to be reimplemented. Attributed titles keep every native behavior and deliver ~80% of the look for ~20% of the effort.
- **Why over leaving it native**: native menus already adapt to light/dark and the system accent, but carry zero brand identity (no green). Attributed titles add the brand green the website shows.

### Decision: Glyph-based dot and checkmark, not the native checkmark state

Render selection as a brand-green "✓" prefix in the attributed title and stop setting `item.state = 1` (the native checkmark, which the OS colors with the system accent and we can't recolor). The status dot is a brand-green "●" prefix on the status line. Exactly one item per submenu carries the "✓".

- **Trade-off**: We give up the native checkmark column alignment. Mitigated by a fixed-width leading glyph + space so rows still align.
- **Alternative considered**: keep `item.state` and accept system-accent checkmarks. Rejected — that's the color we're specifically trying to brand.

### Decision: Appearance-aware color via a small theme helper

Add `src/whispy/ui/menu_theme.py` exposing the accent `NSColor` and helpers to build attributed titles (dot prefix, section header, check prefix). Pick `#24bf9e` (bright) vs `#1c9a7f` (dim) based on the effective appearance (`NSApp.effectiveAppearance` best-match against `NSAppearanceNameDarkAqua`).

- **Refresh on appearance switch**: attributed titles built once won't recolor when the user flips light/dark. Rebuild the accented titles when the menu is about to open (the menu-open hook) so the current appearance is read each time. Keep the rebuild list small (status, header, current checks).
- **Alternative considered**: a dynamic `NSColor` (provider block / asset color). More "correct" but heavier to wire through pyobjc; rebuild-on-open is simpler and the menu is short-lived.

### Decision: Linux untouched, documented

`tray.py` keeps plain labels. Note the limitation in the spec and (optionally) a code comment so future contributors don't try to port attributed titles to pystray.

## Risks / Trade-offs

- **Checkmark alignment drift** (glyph prefix vs native checkmark column) → fixed-width leading glyph + consistent spacing; eyeball against the website.
- **Stale accent color after light/dark switch while app runs** → rebuild accented titles on menu-open so appearance is re-read each time.
- **Low contrast of green on a light menu** → use `--green-dim` in light appearance; verify legibility in both.
- **rumps/pyobjc version drift hiding `setAttributedTitle_`** → already verified present; guard with a capability check that falls back to plain titles if absent (degrade gracefully, never crash the menu).
- **Test reach**: attributed-title rendering can't be asserted headlessly off-macOS → unit-test the pure helpers (color selection by appearance, attributed-string construction, single-check invariant); leave visual rendering to manual macOS check.

## Migration Plan

Purely additive cosmetic change. No data, config, or API impact. Rollback = revert the `menu_bar.py` / `menu_theme.py` edits; native titles return. No user action required.

## Open Questions

- None blocking. Whether to also tint the brand header row ("Whispy · voice dictation") green is a minor aesthetic call — default: leave it native to match the website, which keeps the header muted.

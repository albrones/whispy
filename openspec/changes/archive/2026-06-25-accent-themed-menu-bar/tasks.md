## 1. Theme helper

- [x] 1.1 Create `src/whispy/ui/menu_theme.py` with brand colors (`#24bf9e` bright, `#1c9a7f` dim)
- [x] 1.2 Add `accent_color()` that returns the right `NSColor` for the current effective appearance (dark → bright, light → dim) via `NSApp.effectiveAppearance` best-match against `NSAppearanceNameDarkAqua`
- [x] 1.3 Add `attributed(text, *, accent_ranges=None, letter_spacing=None)` helper building an `NSAttributedString` with the accent color applied to given ranges
- [x] 1.4 Add convenience builders: `status_title(text)` (green "●" prefix), `section_title(text)` (uppercase, green, letter-spaced), `check_title(text, checked)` (green "✓ " prefix or aligned spacer)
- [x] 1.5 Add a capability guard: if `setAttributedTitle_` is unavailable, builders return plain strings so the menu degrades gracefully

## 2. Apply styling in menu_bar.py

- [x] 2.1 Style the status row: set the status item's attributed title via `status_title(...)` in `_build_menu` and in `update_status_display`
- [x] 2.2 Style the "Settings" section header with `section_title("Settings")`
- [x] 2.3 Replace native `item.state = 1` checkmarks with green-glyph attributed titles for Model items (build + on `_on_model_select`)
- [x] 2.4 Same for Language items (build + on `_on_language_select`)
- [x] 2.5 Same for the "Copy to clipboard" toggle (build + on `_on_toggle_copy`)
- [x] 2.6 Enforce single-check invariant per submenu when rebuilding titles

## 3. Appearance refresh

- [x] 3.1 Re-read appearance and rebuild accented titles (status, header, current checks) when light/dark flips. **Note:** implemented via appearance-change detection in the existing always-on `_anim_timer` tick (`_refresh_accents`) rather than an NSMenu `menuWillOpen_` delegate — simpler, no new ObjC class, and recolors even while the menu is closed.
- [x] 3.2 Verify accents recolor correctly after switching system appearance while the app runs

## 4. Linux + docs

- [x] 4.1 Confirm `src/whispy/platform/linux/tray.py` keeps plain labels; add a short comment noting pystray can't render attributed titles
- [x] 4.2 Note the macOS-only theming limitation where platform differences are documented (e.g. docs/PROJECT_MAP.md or README platform notes)

## 5. Tests + manual verification

- [x] 5.1 Unit-test `accent_color()` selection per appearance (mock effective appearance)
- [x] 5.2 Unit-test attributed-title builders (correct ranges, single-check invariant, plain-string fallback)
- [x] 5.3 Manual macOS check: status dot, SETTINGS header, green checkmarks render and update on selection; legible in both light and dark; native hover/dismiss/submenu/keyboard intact _(operator-verified 2026-06-25 — all points pass)_

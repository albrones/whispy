"""Brand-accent styling for the macOS menu bar (attributed titles).

Mirrors the website's menu mockup (``website/styles.css`` ``--green`` /
``--green-dim``): a green status dot, a green uppercase "SETTINGS" header, and
green checkmarks. Styling is applied via ``NSMenuItem.setAttributedTitle_`` so
every native menu behaviour (hover, dismiss, submenu, keyboard) is preserved.

macOS-only cosmetics. All AppKit access is lazy and guarded so importing this
module is safe on Linux/CI: when AppKit is unavailable (or attributed titles are
unsupported) the builders return plain strings and ``apply_title`` falls back to
a plain title. Nothing here ever raises into the menu.
"""

from __future__ import annotations

# Brand palette — mirrors website/styles.css (--green / --green-dim).
GREEN_BRIGHT = (0x24, 0xBF, 0x9E)  # #24bf9e — used on dark menus
GREEN_DIM = (0x1C, 0x9A, 0x7F)  # #1c9a7f — used on light menus (better contrast)

DOT = "●"  # ●  status dot
CHECK = "✓"  # ✓  selection mark


def _appkit():
    """Return the AppKit module, or None when it can't be imported (non-macOS)."""
    try:
        import AppKit

        return AppKit
    except Exception:
        return None


def is_dark_appearance() -> bool:
    """True when the app's effective appearance is dark.

    Defaults to True (dark) when AppKit or the running app is unavailable — the
    brighter green is the safer default and matches the dark website mockup.
    """
    ak = _appkit()
    if ak is None:
        return True
    try:
        app = ak.NSApplication.sharedApplication()
        appearance = app.effectiveAppearance()
        match = appearance.bestMatchFromAppearancesWithNames_(
            [ak.NSAppearanceNameAqua, ak.NSAppearanceNameDarkAqua]
        )
        return match == ak.NSAppearanceNameDarkAqua
    except Exception:
        return True


def accent_color():
    """NSColor for the current appearance, or None when AppKit is unavailable."""
    ak = _appkit()
    if ak is None:
        return None
    r, g, b = GREEN_BRIGHT if is_dark_appearance() else GREEN_DIM
    return ak.NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, 1.0)


def supported() -> bool:
    """True when attributed titles can be built and applied (AppKit present)."""
    ak = _appkit()
    return ak is not None and hasattr(ak, "NSMutableAttributedString")


def attributed(text, *, accent_ranges=None, letter_spacing=None):
    """Build an NSAttributedString applying the accent colour to ``accent_ranges``.

    ``accent_ranges`` is an iterable of ``(start, length)`` tuples. Returns None
    when AppKit is unavailable so callers can fall back to a plain string.
    """
    ak = _appkit()
    if ak is None:
        return None
    s = ak.NSMutableAttributedString.alloc().initWithString_(text)
    color = accent_color()
    if color is not None:
        for start, length in accent_ranges or ():
            s.addAttribute_value_range_(ak.NSForegroundColorAttributeName, color, (start, length))
    if letter_spacing is not None:
        s.addAttribute_value_range_(ak.NSKernAttributeName, letter_spacing, (0, len(text)))
    return s


def status_title(text):
    """Status line with a leading green dot (``● Ready``)."""
    label = f"{DOT}  {text}"
    s = attributed(label, accent_ranges=[(0, 1)])
    return s if s is not None else label


def section_title(text):
    """Section header: uppercase, green, letter-spaced (``SETTINGS``)."""
    label = text.upper()
    s = attributed(label, accent_ranges=[(0, len(label))], letter_spacing=1.5)
    return s if s is not None else label


def check_title(text, checked):
    """Row title with a leading green ✓ when selected, aligned spacer when not.

    The unchecked spacer reserves the same leading width so checked and
    unchecked rows stay aligned (the website reserves a fixed tick column).
    """
    if checked:
        label = f"{CHECK}  {text}"
        s = attributed(label, accent_ranges=[(0, 1)])
        return s if s is not None else label
    # Unchecked: spacer matches "✓  " width; nothing to accent → plain is fine.
    return f"      {text}"


def apply_title(item, value) -> None:
    """Set a rumps MenuItem's title from ``value``.

    ``value`` may be an NSAttributedString (from the builders above) or a plain
    string. Uses ``setAttributedTitle_`` on the underlying NSMenuItem when
    available; otherwise falls back to the plain title so the menu still renders.
    """
    ak = _appkit()
    ns = getattr(item, "_menuitem", None)
    if (
        ak is not None
        and ns is not None
        and hasattr(ns, "setAttributedTitle_")
        and isinstance(value, ak.NSAttributedString)
    ):
        ns.setAttributedTitle_(value)
        return
    # Plain fallback — accept either a str or an attributed string we can't apply.
    item.title = value if isinstance(value, str) else value.string()

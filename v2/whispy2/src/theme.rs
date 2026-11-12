//! Brand-accent styling of the menu, as data (V1's `menu_theme.py`).
//!
//! Mirrors the website's menu mockup: a green status dot, a green uppercase
//! SETTINGS header and green check marks. This module only says *what* to
//! style; `mac/menu_bar.rs` turns a [`Title`] into an attributed string, so
//! the rules stay testable without AppKit.
//!
//! Accent ranges are `(start, length)` in **UTF-16 code units**, because that
//! is what `NSRange` counts. `●` and `✓` are in the BMP, so one char is one
//! unit here, but the offsets are computed in UTF-16 so a title with an
//! astral character before an accent would still be right.

/// An sRGB colour, 0..=255 per channel.
pub type Rgb = (u8, u8, u8);

/// `#24bf9e`, used on dark menus.
pub const GREEN_BRIGHT: Rgb = (0x24, 0xBF, 0x9E);
/// `#1c9a7f`, used on light menus (better contrast).
pub const GREEN_DIM: Rgb = (0x1C, 0x9A, 0x7F);

/// The status dot.
pub const DOT: &str = "●";
/// The selection mark.
pub const CHECK: &str = "✓";

/// Letter spacing of the section header, in points.
pub const SECTION_KERN: f64 = 1.5;

/// The brand green for the menu's appearance.
pub fn accent(dark: bool) -> Rgb {
    if dark {
        GREEN_BRIGHT
    } else {
        GREEN_DIM
    }
}

/// A menu row title: its text, which ranges take the accent colour, and an
/// optional letter spacing for the whole text.
#[derive(Debug, Clone, PartialEq)]
pub struct Title {
    pub text: String,
    /// `(start, length)` in UTF-16 code units.
    pub accents: Vec<(usize, usize)>,
    pub kern: Option<f64>,
}

impl Title {
    /// A title with no styling.
    pub fn plain(text: impl Into<String>) -> Title {
        Title {
            text: text.into(),
            accents: Vec::new(),
            kern: None,
        }
    }
}

fn utf16_len(s: &str) -> usize {
    s.encode_utf16().count()
}

/// The status line: a leading green dot (`●  Ready`).
pub fn status_title(text: &str) -> Title {
    Title {
        text: format!("{DOT}  {text}"),
        accents: vec![(0, utf16_len(DOT))],
        kern: None,
    }
}

/// A section header: uppercase, green, letter-spaced (`SETTINGS`).
pub fn section_title(text: &str) -> Title {
    let label = text.to_uppercase();
    let len = utf16_len(&label);
    Title {
        text: label,
        accents: vec![(0, len)],
        kern: Some(SECTION_KERN),
    }
}

/// A choice: a leading green `✓` when selected, a blank of the same width
/// when not, so checked and unchecked rows stay aligned. The blank is exactly
/// six spaces, as in V1.
pub fn check_title(text: &str, checked: bool) -> Title {
    if checked {
        Title {
            text: format!("{CHECK}  {text}"),
            accents: vec![(0, utf16_len(CHECK))],
            kern: None,
        }
    } else {
        Title::plain(format!("      {text}"))
    }
}

/// A toggle: a TRAILING green `✓` when on, so the title stays left-aligned
/// with the other rows. Plain when off.
pub fn toggle_title(text: &str, checked: bool) -> Title {
    if !checked {
        return Title::plain(text);
    }
    let label = format!("{text}   {CHECK}");
    let start = utf16_len(&label) - utf16_len(CHECK);
    Title {
        text: label,
        accents: vec![(start, utf16_len(CHECK))],
        kern: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accent_follows_the_appearance() {
        assert_eq!(accent(true), (0x24, 0xBF, 0x9E));
        assert_eq!(accent(false), (0x1C, 0x9A, 0x7F));
    }

    #[test]
    fn status_has_a_green_dot() {
        let t = status_title("Ready");
        assert_eq!(t.text, "●  Ready");
        assert_eq!(t.accents, vec![(0, 1)]);
    }

    #[test]
    fn section_is_uppercase_green_and_spaced() {
        let t = section_title("Settings");
        assert_eq!(t.text, "SETTINGS");
        assert_eq!(t.accents, vec![(0, 8)]);
        assert_eq!(t.kern, Some(1.5));
    }

    #[test]
    fn check_title_aligns_checked_and_unchecked() {
        let on = check_title("Fn", true);
        assert_eq!(on.text, "✓  Fn");
        assert_eq!(on.accents, vec![(0, 1)]);
        let off = check_title("Fn", false);
        assert_eq!(off.text, "      Fn");
        assert!(off.accents.is_empty());
    }

    #[test]
    fn toggle_title_ticks_at_the_end() {
        let on = toggle_title("Toggle mode", true);
        assert_eq!(on.text, "Toggle mode   ✓");
        assert_eq!(on.accents, vec![(14, 1)]);
        assert_eq!(
            toggle_title("Toggle mode", false),
            Title::plain("Toggle mode")
        );
    }

    #[test]
    fn accents_count_utf16_units_not_chars() {
        // An astral character is one char but two UTF-16 units.
        let t = toggle_title("😀", true);
        assert_eq!(t.accents, vec![(5, 1)]);
    }
}

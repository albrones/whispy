//! The menu bar title animation: V1's braille waveform.
//!
//! The `WAVEROWS` frames are vendored from unicode-animations by
//! gunnargray-dev (<https://github.com/gunnargray-dev/unicode-animations>),
//! which is MIT licensed, via V1's Python port (`src/whispy/ui/unicode_anim.py`).
//!
//! `WAVEROWS` is a sine wave scrolling left to right across four braille
//! characters; it reads like an audio waveform, which is the brand. The
//! original generator (8x4 dot grid, 16 frames) is
//! `row = round((sin((f - c*0.5) * 0.8) + 1) / 2 * 3)` per column `c` and frame
//! `f`, plus a sparse trailing dot one row above when `(f + c) % 3 == 0`.
//!
//! Pure data and one function, so the frame choice is testable without AppKit:
//! the main-thread timer only asks [`select_frame`] what to show.

use std::time::Duration;

/// 16 scrolling-wave frames, four braille characters each.
pub const WAVEROWS: [&str; 16] = [
    "⠖⠉⠉⠑",
    "⡠⠖⠉⠉",
    "⣠⡠⠖⠉",
    "⣄⣠⡠⠖",
    "⠢⣄⣠⡠",
    "⠙⠢⣄⣠",
    "⠉⠙⠢⣄",
    "⠊⠉⠙⠢",
    "⠜⠊⠉⠙",
    "⡤⠜⠊⠉",
    "⣀⡤⠜⠊",
    "⢤⣀⡤⠜",
    "⠣⢤⣀⡤",
    "⠑⠣⢤⣀",
    "⠉⠑⠣⢤",
    "⠋⠉⠑⠣",
];

/// Frame interval: 90 ms, as in the original library and V1.
pub const INTERVAL: Duration = Duration::from_millis(90);

/// The static frame shown when idle: a calm centred waveform.
pub const IDLE_FRAME: &str = "⣀⣤⣶⣤";

/// The title for tick `index`: the scrolling frame (wrapping) while `active`,
/// the idle frame otherwise. The caller counts ticks and resets to 0 when it
/// goes idle, as V1 does.
pub fn select_frame(index: usize, active: bool) -> &'static str {
    if active {
        WAVEROWS[index % WAVEROWS.len()]
    } else {
        IDLE_FRAME
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn active_frames_wrap_around() {
        assert_eq!(select_frame(0, true), "⠖⠉⠉⠑");
        assert_eq!(select_frame(15, true), "⠋⠉⠑⠣");
        assert_eq!(select_frame(16, true), WAVEROWS[0]);
        assert_eq!(select_frame(35, true), WAVEROWS[3]);
    }

    #[test]
    fn inactive_is_the_idle_frame_whatever_the_index() {
        assert_eq!(select_frame(0, false), "⣀⣤⣶⣤");
        assert_eq!(select_frame(7, false), IDLE_FRAME);
    }

    #[test]
    fn every_frame_is_four_braille_characters() {
        for f in WAVEROWS {
            assert_eq!(f.chars().count(), 4);
            assert!(f.chars().all(|c| ('\u{2800}'..='\u{28FF}').contains(&c)));
        }
        assert_eq!(INTERVAL.as_millis(), 90);
    }
}

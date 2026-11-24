//! The recording pill's maths: V1's `waveform_window.py`, without AppKit.
//!
//! The level curve, the bar heights and the placement are pure functions, so
//! they are tested here; `mac/pill.rs` only feeds them a clock and draws what
//! they return. Coordinates follow AppKit: origin at the bottom left, y up.

/// A rectangle as `(x, y, width, height)`.
pub type Rect = (f64, f64, f64, f64);

pub const PILL_WIDTH: f64 = 168.0;
pub const PILL_HEIGHT: f64 = 52.0;
pub const BAR_COUNT: usize = 11;
pub const BAR_WIDTH: f64 = 5.0;
pub const BAR_GAP: f64 = 6.0;
pub const BAR_MIN_HEIGHT: f64 = 5.0;
pub const BAR_MAX_HEIGHT: f64 = 38.0;
/// Perceptual boost: lift quiet speech so the bars are lively (gamma < 1 + gain).
pub const LEVEL_GAMMA: f64 = 0.5;
pub const LEVEL_GAIN: f64 = 2.0;
/// Distance from the bottom of the visible screen, in points.
pub const BOTTOM_MARGIN: f64 = 40.0;
pub const FPS: f64 = 30.0;
/// Higher is a snappier fade in and out.
pub const FADE_SPEED: f64 = 4.5;
/// Below this alpha, a fading-out pill is ordered out.
pub const HIDE_BELOW_ALPHA: f64 = 0.02;
/// Pill background, sRGB with alpha.
pub const BACKGROUND: (f64, f64, f64, f64) = (0.07, 0.07, 0.09, 0.92);

/// V1's level scale from a block's RMS: `min(rms * 10, 1)`.
pub fn level_from_rms(rms: f64) -> f64 {
    (rms * 10.0).min(1.0)
}

/// Moves the displayed `level` toward `target` by `dt * 8` of the gap (capped
/// at the whole gap). `target` is clamped to 0..=1 first, as V1 does.
pub fn smooth(level: f64, target: f64, dt: f64) -> f64 {
    let target = target.clamp(0.0, 1.0);
    level + (target - level) * (dt * 8.0).min(1.0)
}

/// The wobble phase after `dt` seconds (`dt * 6`).
pub fn advance_phase(phase: f64, dt: f64) -> f64 {
    phase + dt * 6.0
}

/// The window opacity after `dt` seconds, easing toward `target`.
pub fn fade_step(fade: f64, target: f64, dt: f64) -> f64 {
    fade + (target - fade) * (dt * FADE_SPEED).min(1.0)
}

/// The level the bars show: gamma and gain applied, capped at 1.
pub fn display_level(level: f64) -> f64 {
    (level.max(0.0).powf(LEVEL_GAMMA) * LEVEL_GAIN).min(1.0)
}

/// The eleven bar heights: a symmetric envelope (taller in the middle) times a
/// per-bar animated wobble, scaled by the displayed level.
pub fn bar_heights(level: f64, phase: f64) -> [f64; BAR_COUNT] {
    let disp = display_level(level);
    let half = (BAR_COUNT - 1) as f64 / 2.0;
    let mut out = [0.0; BAR_COUNT];
    for (i, h) in out.iter_mut().enumerate() {
        let envelope = 1.0 - (i as f64 - half).abs() / half;
        let envelope = 0.45 + 0.55 * envelope;
        let wobble = 0.5 + 0.5 * (phase + i as f64 * 0.9).sin();
        let amount = disp * envelope * (0.6 + 0.4 * wobble);
        *h = BAR_MIN_HEIGHT + (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT) * amount;
    }
    out
}

/// Each bar's rectangle in a view of `width` x `height`: centred horizontally,
/// and vertically in the top [`PILL_HEIGHT`] points (the whole view when it is the
/// plain pill, the part above the caption row when it is the captioned one).
/// The corner radius is half the bar width.
pub fn bar_rects(width: f64, height: f64, heights: &[f64; BAR_COUNT]) -> [Rect; BAR_COUNT] {
    let total_w = BAR_COUNT as f64 * BAR_WIDTH + (BAR_COUNT - 1) as f64 * BAR_GAP;
    let start_x = (width - total_w) / 2.0;
    let mid_y = height - PILL_HEIGHT / 2.0;
    let mut out = [(0.0, 0.0, 0.0, 0.0); BAR_COUNT];
    for (i, r) in out.iter_mut().enumerate() {
        let h = heights[i];
        *r = (
            start_x + i as f64 * (BAR_WIDTH + BAR_GAP),
            mid_y - h / 2.0,
            BAR_WIDTH,
            h,
        );
    }
    out
}

/// The bar colour: brand green `#24bf9e` that brightens with the level,
/// sRGB with alpha 0.95.
pub fn bar_color(level: f64) -> (f64, f64, f64, f64) {
    (
        (0.141 + 0.10 * level).min(1.0),
        (0.749 + 0.15 * level).min(1.0),
        (0.620 + 0.10 * level).min(1.0),
        0.95,
    )
}

/// Where the plain pill's origin goes in a screen's visible frame `(x, y, w, h)`:
/// centred horizontally, [`BOTTOM_MARGIN`] above the bottom.
pub fn pill_origin(visible: Rect) -> (f64, f64) {
    (
        visible.0 + (visible.2 - PILL_WIDTH) / 2.0,
        visible.1 + BOTTOM_MARGIN,
    )
}

/// Width of the pill once it carries a caption (a type-while-speaking recording).
pub const CAPTION_PILL_WIDTH: f64 = 560.0;
/// Height of the caption row, below the bars.
pub const CAPTION_ROW_HEIGHT: f64 = 26.0;
/// Space kept free left and right of the caption.
pub const CAPTION_SIDE_PADDING: f64 = 16.0;
/// System font size of the caption, in points.
pub const CAPTION_FONT_SIZE: f64 = 14.0;
/// Height of one line of the caption font (14 pt system font: about 17 pt).
pub const CAPTION_LINE_HEIGHT: f64 = 18.0;
/// Opacity of the committed words (white).
pub const CAPTION_COMMITTED_ALPHA: f64 = 0.95;
/// Opacity of the words heard but not committed yet (white).
pub const CAPTION_PROVISIONAL_ALPHA: f64 = 0.5;
/// The background's corner radius: V1's, half the plain pill's height, kept for the
/// taller captioned pill so its corners do not bulge into the caption row.
pub const CORNER_RADIUS: f64 = PILL_HEIGHT / 2.0;

/// The panel's size: the plain pill, or the captioned one (wider, with the caption
/// row below the bars), which then keeps it until the recording ends.
pub fn pill_size(captioned: bool) -> (f64, f64) {
    if captioned {
        (CAPTION_PILL_WIDTH, PILL_HEIGHT + CAPTION_ROW_HEIGHT)
    } else {
        (PILL_WIDTH, PILL_HEIGHT)
    }
}

/// The panel's frame in a screen's visible frame. Horizontally centred; the top
/// edge is the plain pill's (so the bars never move) and the captioned panel
/// extends downward from it.
pub fn pill_frame(visible: Rect, captioned: bool) -> Rect {
    let (_, y) = pill_origin(visible);
    let top = y + PILL_HEIGHT;
    let (width, height) = pill_size(captioned);
    (
        visible.0 + (visible.2 - width) / 2.0,
        top - height,
        width,
        height,
    )
}

/// The caption's rectangle in a panel `width` wide: the bottom row, side padding
/// each side, one line high, vertically centred in the row.
pub fn caption_text_rect(width: f64) -> Rect {
    (
        CAPTION_SIDE_PADDING,
        (CAPTION_ROW_HEIGHT - CAPTION_LINE_HEIGHT) / 2.0,
        (width - 2.0 * CAPTION_SIDE_PADDING).max(0.0),
        CAPTION_LINE_HEIGHT,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn silence_draws_minimum_bars() {
        for h in bar_heights(0.0, 1.3) {
            assert_eq!(h, BAR_MIN_HEIGHT);
        }
    }

    #[test]
    fn middle_bar_is_taller_and_everything_stays_in_range() {
        // A phase that makes every wobble equal: sin(phase + i*0.9) varies per
        // bar, so compare the envelope with a flat phase approximation instead.
        let hs = bar_heights(0.5, 0.0);
        for h in hs {
            assert!((BAR_MIN_HEIGHT..=BAR_MAX_HEIGHT).contains(&h));
        }
        let centre: f64 = (0..200).map(|k| bar_heights(0.5, k as f64 * 0.1)[5]).sum();
        let edge: f64 = (0..200).map(|k| bar_heights(0.5, k as f64 * 0.1)[0]).sum();
        assert!(centre > edge);
        assert!(
            *bar_heights(1.0, 0.7)
                .iter()
                .max_by(|a, b| a.total_cmp(b))
                .unwrap()
                <= BAR_MAX_HEIGHT
        );
    }

    #[test]
    fn level_scale_matches_v1() {
        assert_eq!(level_from_rms(0.0), 0.0);
        assert!((level_from_rms(0.05) - 0.5).abs() < 1e-12);
        assert_eq!(level_from_rms(0.5), 1.0);
        assert_eq!(display_level(0.25), 1.0); // sqrt(0.25) * 2
        assert!((display_level(0.04) - 0.4).abs() < 1e-12);
    }

    #[test]
    fn smoothing_and_fade_ease_toward_their_target() {
        assert!((smooth(0.0, 1.0, 1.0 / FPS) - 8.0 / 30.0).abs() < 1e-12);
        assert_eq!(smooth(0.2, 1.0, 1.0), 1.0); // capped at the whole gap
        assert_eq!(smooth(0.0, 5.0, 1.0), 1.0); // target clamped
        assert!((fade_step(0.0, 1.0, 0.1) - 0.45).abs() < 1e-12);
        assert!((advance_phase(1.0, 0.5) - 4.0).abs() < 1e-12);
    }

    #[test]
    fn bars_are_centred_in_the_pill() {
        let rects = bar_rects(PILL_WIDTH, PILL_HEIGHT, &[BAR_MIN_HEIGHT; BAR_COUNT]);
        let first = rects[0];
        let last = rects[BAR_COUNT - 1];
        // Left and right margins are equal.
        assert!((first.0 - (PILL_WIDTH - (last.0 + last.2))).abs() < 1e-9);
        assert!((first.1 + first.3 / 2.0 - PILL_HEIGHT / 2.0).abs() < 1e-9);
        assert_eq!(first.2, BAR_WIDTH);
        assert_eq!(rects[1].0 - rects[0].0, BAR_WIDTH + BAR_GAP);
    }

    #[test]
    fn pill_is_centred_forty_up_in_the_visible_frame() {
        assert_eq!(
            pill_origin((0.0, 0.0, 1440.0, 875.0)),
            ((1440.0 - 168.0) / 2.0, 40.0)
        );
        // A secondary screen or a Dock-reduced frame offsets both axes.
        assert_eq!(
            pill_origin((1440.0, 70.0, 1000.0, 800.0)),
            (1440.0 + 416.0, 110.0)
        );
    }

    #[test]
    fn colour_at_silence_is_the_brand_green() {
        let (r, g, b, a) = bar_color(0.0);
        assert_eq!(
            (
                (r * 255.0).round() as u8,
                (g * 255.0).round() as u8,
                (b * 255.0).round() as u8
            ),
            (0x24, 0xBF, 0x9E)
        );
        assert_eq!(a, 0.95);
        let (r1, g1, _, _) = bar_color(1.0);
        assert!(r1 > r && g1 > g);
    }

    #[test]
    fn the_plain_frame_is_the_plain_pill() {
        let visible = (0.0, 25.0, 1440.0, 875.0);
        assert_eq!(
            pill_frame(visible, false),
            ((1440.0 - 168.0) / 2.0, 25.0 + BOTTOM_MARGIN, 168.0, 52.0)
        );
    }

    #[test]
    fn the_captioned_frame_hangs_from_the_plain_top_edge_and_stays_centred() {
        let visible = (100.0, 25.0, 1440.0, 875.0);
        let plain = pill_frame(visible, false);
        let (x, y, w, h) = pill_frame(visible, true);
        assert_eq!(w, 560.0);
        assert_eq!(h, PILL_HEIGHT + CAPTION_ROW_HEIGHT);
        assert_eq!(y + h, plain.1 + plain.3); // same top edge
        assert_eq!(y, plain.1 - CAPTION_ROW_HEIGHT); // bottom moved down by the row
        assert_eq!(x + w / 2.0, plain.0 + plain.2 / 2.0); // same centre axis
        assert_eq!(x + w / 2.0, 100.0 + 1440.0 / 2.0);
    }

    #[test]
    fn the_bars_are_centred_in_the_top_52_points_of_the_captioned_panel() {
        let heights = bar_heights(0.4, 0.7);
        let (_, _, w, h) = pill_frame((0.0, 0.0, 1440.0, 875.0), true);
        let rects = bar_rects(w, h, &heights);
        let (first, last) = (rects[0], rects[BAR_COUNT - 1]);
        assert!((first.0 - (w - (last.0 + last.2))).abs() < 1e-9);
        for (r, bar_h) in rects.iter().zip(heights) {
            // Centre line 26 pt below the panel top, as in the plain pill.
            assert!((h - (r.1 + bar_h / 2.0) - PILL_HEIGHT / 2.0).abs() < 1e-9);
            assert!(r.1 >= h - PILL_HEIGHT && r.1 + r.3 <= h);
        }
        // Without a caption the bars are where they always were.
        let plain = bar_rects(PILL_WIDTH, PILL_HEIGHT, &heights);
        assert!((plain[0].1 + plain[0].3 / 2.0 - PILL_HEIGHT / 2.0).abs() < 1e-9);
    }

    #[test]
    fn the_caption_sits_in_the_bottom_row_with_sixteen_points_each_side() {
        let (x, y, w, h) = caption_text_rect(CAPTION_PILL_WIDTH);
        assert_eq!(x, 16.0);
        assert_eq!(x + w, CAPTION_PILL_WIDTH - 16.0);
        assert_eq!(y + h / 2.0, CAPTION_ROW_HEIGHT / 2.0);
        assert!(y >= 0.0 && y + h <= CAPTION_ROW_HEIGHT);
    }

    #[test]
    fn committed_words_are_brighter_than_provisional_ones() {
        assert_eq!(CAPTION_COMMITTED_ALPHA, 0.95);
        assert_eq!(CAPTION_PROVISIONAL_ALPHA, 0.5);
    }
}

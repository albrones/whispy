//! The recording pill's maths: V1's `waveform_window.py`, without AppKit.
//!
//! The level curve, the bar heights, the caption layout and the placement are pure functions, so
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

/// Linear blend from `from` (progress 0) to `to` (progress 1).
fn lerp(from: f64, to: f64, progress: f64) -> f64 {
    from + (to - from) * progress.clamp(0.0, 1.0)
}

/// Height range of the bars `(min, max)` at a caption `progress`: V1's 5 to 38 pt
/// at 0, shrinking to [`CAPTION_BAR_MIN_HEIGHT`] to [`CAPTION_BAR_MAX_HEIGHT`] at 1.
pub fn bar_height_range(progress: f64) -> (f64, f64) {
    (
        lerp(BAR_MIN_HEIGHT, CAPTION_BAR_MIN_HEIGHT, progress),
        lerp(BAR_MAX_HEIGHT, CAPTION_BAR_MAX_HEIGHT, progress),
    )
}

/// Distance of the bars' vertical centre from the pill's bottom at a caption
/// `progress`: the pill's middle at 0, [`CAPTION_BAR_CENTRE`] at 1.
pub fn bar_centre_y(progress: f64) -> f64 {
    lerp(PILL_HEIGHT / 2.0, CAPTION_BAR_CENTRE, progress)
}

/// The eleven bar heights: a symmetric envelope (taller in the middle) times a
/// per-bar animated wobble, scaled by the displayed level, within the range that
/// the caption `progress` allows.
pub fn bar_heights(level: f64, phase: f64, progress: f64) -> [f64; BAR_COUNT] {
    let disp = display_level(level);
    let (min, max) = bar_height_range(progress);
    let half = (BAR_COUNT - 1) as f64 / 2.0;
    let mut out = [0.0; BAR_COUNT];
    for (i, h) in out.iter_mut().enumerate() {
        let envelope = 1.0 - (i as f64 - half).abs() / half;
        let envelope = 0.45 + 0.55 * envelope;
        let wobble = 0.5 + 0.5 * (phase + i as f64 * 0.9).sin();
        let amount = disp * envelope * (0.6 + 0.4 * wobble);
        *h = min + (max - min) * amount;
    }
    out
}

/// Each bar's rectangle in the pill: centred horizontally, and vertically on
/// [`bar_centre_y`] for the caption `progress`. The corner radius is half the bar width.
pub fn bar_rects(heights: &[f64; BAR_COUNT], progress: f64) -> [Rect; BAR_COUNT] {
    let total_w = BAR_COUNT as f64 * BAR_WIDTH + (BAR_COUNT - 1) as f64 * BAR_GAP;
    let start_x = (PILL_WIDTH - total_w) / 2.0;
    let mid_y = bar_centre_y(progress);
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

/// Vertical centre of the bars, from the pill's bottom, once the caption is fully shown.
pub const CAPTION_BAR_CENTRE: f64 = 33.0;
/// Bar height range once the caption is fully shown: top edge at most 44 pt, bottom
/// edge at least 22 pt up, so the tallest bar stays 3 pt above the text.
pub const CAPTION_BAR_MIN_HEIGHT: f64 = 4.0;
pub const CAPTION_BAR_MAX_HEIGHT: f64 = 22.0;
/// Space kept free left and right of the caption.
pub const CAPTION_SIDE_PADDING: f64 = 10.0;
/// Bottom edge of the caption line, from the pill's bottom.
pub const CAPTION_BOTTOM: f64 = 5.0;
/// Height of the caption line (11 pt system font: about 13 pt), so it spans 5 to 19 pt.
pub const CAPTION_LINE_HEIGHT: f64 = 14.0;
/// System font size of the caption, in points.
pub const CAPTION_FONT_SIZE: f64 = 11.0;
/// Opacity of the committed words (white).
pub const CAPTION_COMMITTED_ALPHA: f64 = 0.95;
/// Opacity of the words heard but not committed yet (white).
pub const CAPTION_PROVISIONAL_ALPHA: f64 = 0.5;
/// Higher is a snappier move to the captioned layout (about 0.25 s to settle).
pub const CAPTION_SPEED: f64 = 14.0;
/// Within this distance of its target, the caption progress lands on it.
const CAPTION_SETTLE: f64 = 0.01;
/// The background's corner radius: V1's, half the pill's height.
pub const CORNER_RADIUS: f64 = PILL_HEIGHT / 2.0;

/// The caption progress (0 = V1's plain pill, 1 = the captioned layout) after `dt`
/// seconds, easing toward `target` like the fade and landing on it once close.
pub fn caption_step(progress: f64, target: f64, dt: f64) -> f64 {
    let next = progress + (target - progress) * (dt * CAPTION_SPEED).min(1.0);
    if (target - next).abs() < CAPTION_SETTLE {
        target
    } else {
        next
    }
}

/// The caption's rectangle in the pill: one line along the bottom, side padding each side.
pub fn caption_text_rect() -> Rect {
    (
        CAPTION_SIDE_PADDING,
        CAPTION_BOTTOM,
        PILL_WIDTH - 2.0 * CAPTION_SIDE_PADDING,
        CAPTION_LINE_HEIGHT,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn silence_draws_minimum_bars() {
        for h in bar_heights(0.0, 1.3, 0.0) {
            assert_eq!(h, BAR_MIN_HEIGHT);
        }
    }

    #[test]
    fn middle_bar_is_taller_and_everything_stays_in_range() {
        // A phase that makes every wobble equal: sin(phase + i*0.9) varies per
        // bar, so compare the envelope with a flat phase approximation instead.
        let hs = bar_heights(0.5, 0.0, 0.0);
        for h in hs {
            assert!((BAR_MIN_HEIGHT..=BAR_MAX_HEIGHT).contains(&h));
        }
        let centre: f64 = (0..200)
            .map(|k| bar_heights(0.5, k as f64 * 0.1, 0.0)[5])
            .sum();
        let edge: f64 = (0..200)
            .map(|k| bar_heights(0.5, k as f64 * 0.1, 0.0)[0])
            .sum();
        assert!(centre > edge);
        assert!(
            *bar_heights(1.0, 0.7, 0.0)
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
        let rects = bar_rects(&[BAR_MIN_HEIGHT; BAR_COUNT], 0.0);
        let first = rects[0];
        let last = rects[BAR_COUNT - 1];
        // Left and right margins are equal.
        assert!((first.0 - (PILL_WIDTH - (last.0 + last.2))).abs() < 1e-9);
        assert!((first.1 + first.3 / 2.0 - PILL_HEIGHT / 2.0).abs() < 1e-9);
        assert_eq!(first.2, BAR_WIDTH);
        assert_eq!(rects[1].0 - rects[0].0, BAR_WIDTH + BAR_GAP);
    }

    #[test]
    fn at_progress_zero_the_bars_are_v1s() {
        assert_eq!(bar_height_range(0.0), (5.0, 38.0));
        assert_eq!(bar_centre_y(0.0), 26.0);
        assert_eq!(bar_heights(0.0, 1.3, 0.0), [5.0; BAR_COUNT]);
        let hs = bar_heights(1.0, 0.7, 0.0);
        assert!(hs.iter().all(|h| (5.0..=38.0).contains(h)));
    }

    #[test]
    fn at_progress_one_the_bars_are_the_captioned_ones() {
        assert_eq!(bar_height_range(1.0), (4.0, 22.0));
        assert_eq!(bar_centre_y(1.0), 33.0);
        assert_eq!(bar_heights(0.0, 0.3, 1.0), [4.0; BAR_COUNT]);
        // Same width and gaps as always.
        let rects = bar_rects(&bar_heights(0.5, 0.2, 1.0), 1.0);
        assert_eq!(rects[0].2, BAR_WIDTH);
        assert_eq!(rects[1].0 - rects[0].0, BAR_WIDTH + BAR_GAP);
    }

    #[test]
    fn the_layout_moves_monotonically_with_the_progress() {
        let mut prev = (bar_centre_y(0.0), bar_height_range(0.0));
        for k in 1..=20 {
            let p = f64::from(k) / 20.0;
            let now = (bar_centre_y(p), bar_height_range(p));
            assert!(now.0 > prev.0, "centre rises");
            assert!(now.1 .0 < prev.1 .0, "min height shrinks");
            assert!(now.1 .1 < prev.1 .1, "max height shrinks");
            prev = now;
        }
        // Out-of-range progress is clamped.
        assert_eq!(bar_centre_y(2.0), bar_centre_y(1.0));
        assert_eq!(bar_centre_y(-1.0), bar_centre_y(0.0));
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
    fn the_caption_is_one_line_along_the_bottom_with_ten_points_each_side() {
        let (x, y, w, h) = caption_text_rect();
        assert_eq!((x, y), (10.0, 5.0));
        assert_eq!(x + w, PILL_WIDTH - 10.0);
        assert_eq!(y + h, 19.0);
        assert!(y >= 0.0 && y + h <= PILL_HEIGHT);
    }

    #[test]
    fn at_full_progress_and_max_level_the_bars_stay_above_the_text() {
        let (_, text_y, _, text_h) = caption_text_rect();
        for k in 0..400 {
            let rects = bar_rects(&bar_heights(1.0, f64::from(k) * 0.05, 1.0), 1.0);
            for (_, y, _, h) in rects {
                assert!(y > text_y + text_h, "bar bottom {y} overlaps the text");
                assert!(y + h <= PILL_HEIGHT, "bar top leaves the pill");
            }
        }
    }

    #[test]
    fn the_caption_progress_eases_and_settles_within_a_third_of_a_second() {
        let mut p = 0.0;
        let mut last = p;
        let mut frames = 0;
        while p < 1.0 {
            p = caption_step(p, 1.0, 1.0 / FPS);
            assert!(p > last && p <= 1.0);
            last = p;
            frames += 1;
            assert!(frames < 20);
        }
        assert!(f64::from(frames) / FPS <= 0.34);
        assert_eq!(caption_step(1.0, 1.0, 0.1), 1.0);
        // And back to V1's look, never past it.
        assert_eq!(caption_step(0.004, 0.0, 1.0 / FPS), 0.0);
        assert_eq!(caption_step(0.5, 0.0, 10.0), 0.0);
    }

    #[test]
    fn committed_words_are_brighter_than_provisional_ones() {
        assert_eq!(CAPTION_COMMITTED_ALPHA, 0.95);
        assert_eq!(CAPTION_PROVISIONAL_ALPHA, 0.5);
    }
}

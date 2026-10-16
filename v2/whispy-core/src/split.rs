//! Splitting a long dictation into pieces an engine takes in one call.
//!
//! Memory grows with the length of one model call: V1 measured Parakeet's
//! peak RSS at 1268 MB for 8 s, 1476 MB for 30 s and 3503 MB for 180 s, and
//! the 180 s clip under CoreML took the machine down. A bounded piece bounds
//! memory whatever the dictation's length.

use std::ops::Range;

use crate::audio::SAMPLE_RATE;
use crate::vad;

/// Longest piece handed to an engine in one call.
pub const MAX_PIECE_S: f32 = 20.0;

/// How far back from the piece limit a pause is looked for.
const PAUSE_SEARCH_S: f32 = 8.0;

/// Ranges of `samples`, each at most `max_piece_s` long, covering every
/// sample exactly once and in order. A cut lands in the middle of the
/// longest run of unvoiced frames in the last `PAUSE_SEARCH_S` before the
/// limit, so a word is not cut in two; with no pause there, it is a hard cut.
pub fn pieces(samples: &[f32], max_piece_s: f32) -> Vec<Range<usize>> {
    let max_len = (max_piece_s * SAMPLE_RATE as f32) as usize;
    let mut ranges = Vec::new();
    let mut start = 0;
    if samples.len() <= max_len || max_len == 0 {
        ranges.push(start..samples.len());
        return ranges;
    }
    let frame_len = (vad::frame_seconds() * SAMPLE_RATE as f32) as usize;
    let voiced = vad::voiced_frames(samples);
    let search_frames = (PAUSE_SEARCH_S * SAMPLE_RATE as f32) as usize / frame_len;

    while samples.len() - start > max_len {
        let limit_frame = (start + max_len) / frame_len;
        let first_frame = limit_frame
            .saturating_sub(search_frames)
            .max(start.div_ceil(frame_len) + 1);
        let cut = longest_pause_middle(&voiced, first_frame, limit_frame)
            .map(|frame| frame * frame_len)
            .unwrap_or(start + max_len);
        ranges.push(start..cut);
        start = cut;
    }
    ranges.push(start..samples.len());
    ranges
}

/// Middle frame of the longest unvoiced run within `first..end`.
fn longest_pause_middle(voiced: &[bool], first: usize, end: usize) -> Option<usize> {
    let end = end.min(voiced.len());
    let first = first.min(end);
    let mut best: Option<(usize, usize)> = None; // (run length, run start)
    let mut run_start = None;
    // A trailing `true` closes a pause that runs to the end of the window.
    let window = voiced[first..end].iter().chain(std::iter::once(&true));
    for (offset, &is_voiced) in window.enumerate() {
        let frame = first + offset;
        let is_pause = !is_voiced;
        match (is_pause, run_start) {
            (true, None) => run_start = Some(frame),
            (false, Some(begin)) => {
                let length = frame - begin;
                if best.is_none_or(|(best_length, _)| length > best_length) {
                    best = Some((length, begin));
                }
                run_start = None;
            }
            _ => {}
        }
    }
    best.map(|(length, begin)| begin + length / 2)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn covers_everything_once(ranges: &[Range<usize>], len: usize) {
        assert_eq!(ranges.first().unwrap().start, 0);
        assert_eq!(ranges.last().unwrap().end, len);
        for pair in ranges.windows(2) {
            assert_eq!(pair[0].end, pair[1].start);
        }
    }

    #[test]
    fn short_audio_is_one_piece() {
        assert_eq!(pieces(&vec![0.0; 1000], MAX_PIECE_S), vec![0..1000]);
    }

    #[test]
    fn long_audio_is_bounded_and_complete() {
        let len = 75 * SAMPLE_RATE as usize + 123;
        let samples = vec![0.0; len];
        let ranges = pieces(&samples, MAX_PIECE_S);
        covers_everything_once(&ranges, len);
        let max_len = (MAX_PIECE_S * SAMPLE_RATE as f32) as usize;
        assert!(
            ranges.iter().all(|range| range.len() <= max_len),
            "{ranges:?}"
        );
        assert!(ranges.len() >= 4);
    }

    #[test]
    fn the_cut_lands_in_the_longest_pause() {
        let voiced = vec![true, true, false, true, false, false, false, true, true];
        assert_eq!(longest_pause_middle(&voiced, 0, voiced.len()), Some(5));
        assert_eq!(longest_pause_middle(&[true, true], 0, 2), None);
    }
}

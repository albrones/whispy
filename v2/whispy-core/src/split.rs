//! Splitting a long dictation into pieces an engine takes in one call.
//!
//! Memory grows with the length of one model call: V1 measured Parakeet's
//! peak RSS at 1268 MB for 8 s, 1476 MB for 30 s and 3503 MB for 180 s, and
//! the 180 s clip under CoreML took the machine down. A bounded piece bounds
//! memory whatever the dictation's length.
//!
//! [`pieces`] splits a finished recording; [`LiveSplitter`] splits one while it
//! is recorded, at the speaker's pauses, so each piece can be typed before the
//! dictation ends (V1's « Type while speaking », `core/segmentation.py`).

use std::ops::Range;

use crate::audio::SAMPLE_RATE;
use crate::vad::{self, VoiceDetector, FRAME_SAMPLES};

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

/// Silence that closes a piece once it holds enough speech (V1's `pause_ms`, 600).
pub const PAUSE_S: f32 = 0.6;
/// Voiced seconds a piece needs before a pause may close it (V1's `min_speech_s`):
/// each piece is one model call, and V1 measured an isolated « oui » (0.39 s
/// voiced) come back in English 5 times out of 5, against 0 at 0.72 s. A short
/// word therefore rides along with the speech after it.
pub const MIN_SPEECH_S: f32 = 0.7;
/// Past this much silence the speaker has stopped: a short word goes alone
/// rather than wait for speech that may never come (V1's `LONE_WORD_PAUSE_S`).
pub const LONE_WORD_PAUSE_S: f32 = 2.0;

/// Splits a recording while it is recorded. Feed it the samples as they come
/// ([`push`](LiveSplitter::push)); it hands back each piece a pause closed, in
/// order; [`finish`](LiveSplitter::finish) gives the rest at the stop. The
/// pieces and the rest, put end to end, are exactly the samples pushed: audio
/// is never dropped, only cut.
///
/// A piece closes when [`PAUSE_S`] of silence follows at least [`MIN_SPEECH_S`]
/// of voiced audio (or [`LONE_WORD_PAUSE_S`] follows any), and in any case
/// before [`MAX_PIECE_S`], in the longest pause of its last seconds, as
/// [`pieces`] cuts. Not `Send` (it holds a [`VoiceDetector`]).
pub struct LiveSplitter {
    /// Samples since the last cut.
    pending: Vec<f32>,
    /// One voiced flag per complete frame of `pending`.
    voiced: Vec<bool>,
    detector: VoiceDetector,
}

impl Default for LiveSplitter {
    fn default() -> Self {
        LiveSplitter::new()
    }
}

impl LiveSplitter {
    pub fn new() -> Self {
        LiveSplitter {
            pending: Vec::new(),
            voiced: Vec::new(),
            detector: VoiceDetector::new(),
        }
    }

    /// Appends `samples` (16 kHz mono) and returns the pieces now closed, in order.
    pub fn push(&mut self, samples: &[f32]) -> Vec<Vec<f32>> {
        self.pending.extend_from_slice(samples);
        let mut closed = Vec::new();
        loop {
            let start = self.voiced.len() * FRAME_SAMPLES;
            let Some(frame) = self.pending.get(start..start + FRAME_SAMPLES) else {
                return closed;
            };
            let frame: &[f32; FRAME_SAMPLES] = frame.try_into().expect("a frame-long slice");
            let is_voiced = self.detector.is_voiced(frame);
            self.voiced.push(is_voiced);
            if let Some(cut) = self.cut_frame() {
                let piece: Vec<f32> = self.pending.drain(..cut * FRAME_SAMPLES).collect();
                self.voiced.drain(..cut);
                closed.push(piece);
            }
        }
    }

    /// The samples after the last piece: the end of the dictation.
    pub fn finish(self) -> Vec<f32> {
        self.pending
    }

    /// The frame to cut before, if the frames classified so far close a piece.
    // ponytail: recounts the piece's frames at each new frame; a piece is at
    // most MAX_PIECE_S (667 frames), so this stays well under a millisecond.
    fn cut_frame(&self) -> Option<usize> {
        let frames = self.voiced.len();
        let frame_s = vad::frame_seconds();
        let voiced_s = self.voiced.iter().filter(|&&voiced| voiced).count() as f32 * frame_s;
        let silence_s = self
            .voiced
            .iter()
            .rev()
            .take_while(|&&voiced| !voiced)
            .count() as f32
            * frame_s;
        let is_pause_closing = voiced_s > 0.0
            && silence_s >= PAUSE_S
            && (voiced_s >= MIN_SPEECH_S || silence_s >= LONE_WORD_PAUSE_S);
        if is_pause_closing {
            return Some(frames);
        }
        let max_frames = (MAX_PIECE_S * SAMPLE_RATE as f32) as usize / FRAME_SAMPLES;
        if frames < max_frames {
            return None;
        }
        let search_frames = (PAUSE_SEARCH_S / frame_s) as usize;
        let first = frames.saturating_sub(search_frames).max(1);
        Some(longest_pause_middle(&self.voiced, first, frames).unwrap_or(frames))
    }
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

    /// Harmonic stack: reads as voiced to WebRTC VAD (see `vad` tests).
    fn voiced(seconds: f32) -> Vec<f32> {
        let count = (seconds * SAMPLE_RATE as f32) as usize;
        (0..count)
            .map(|i| {
                let t = i as f32 / SAMPLE_RATE as f32;
                (1..=10)
                    .map(|h| 0.03 * (2.0 * std::f32::consts::PI * 150.0 * h as f32 * t).sin())
                    .sum::<f32>()
            })
            .collect()
    }

    fn silence(seconds: f32) -> Vec<f32> {
        vec![0.0; (seconds * SAMPLE_RATE as f32) as usize]
    }

    /// Pushes `samples` in 50 ms blocks, as the microphone delivers them.
    fn split_live(samples: &[f32]) -> (Vec<Vec<f32>>, Vec<f32>) {
        let mut splitter = LiveSplitter::new();
        let mut closed = Vec::new();
        for block in samples.chunks(800) {
            closed.extend(splitter.push(block));
        }
        (closed, splitter.finish())
    }

    fn joined(closed: &[Vec<f32>], rest: &[f32]) -> Vec<f32> {
        closed.iter().flatten().chain(rest).copied().collect()
    }

    #[test]
    fn a_one_second_pause_closes_a_piece_while_recording() {
        let clip = [voiced(1.5), silence(1.0), voiced(1.5), silence(0.2)].concat();
        let (closed, rest) = split_live(&clip);
        assert_eq!(
            closed.len(),
            1,
            "{:?}",
            closed.iter().map(Vec::len).collect::<Vec<_>>()
        );
        // Closed once the pause reached PAUSE_S, give or take the VAD's own
        // hangover (a few frames still read as voiced after the voice stops).
        let first_s = closed[0].len() as f32 / SAMPLE_RATE as f32;
        assert!(
            (1.5 + PAUSE_S..1.5 + PAUSE_S + 0.3).contains(&first_s),
            "{first_s}"
        );
        assert_eq!(joined(&closed, &rest), clip, "every sample kept, in order");
    }

    #[test]
    fn a_short_word_rides_along_with_what_follows() {
        let clip = [voiced(0.4), silence(0.8), voiced(1.5), silence(0.2)].concat();
        let (closed, rest) = split_live(&clip);
        assert!(closed.is_empty(), "{} pieces", closed.len());
        assert_eq!(rest, clip);
        // But after LONE_WORD_PAUSE_S the speaker has stopped: the word goes alone.
        let clip = [voiced(0.4), silence(2.2), voiced(1.0)].concat();
        let (closed, rest) = split_live(&clip);
        assert_eq!(closed.len(), 1);
        assert_eq!(joined(&closed, &rest), clip);
    }

    #[test]
    fn run_on_speech_is_cut_before_the_piece_limit() {
        let clip = voiced(45.0);
        let (closed, rest) = split_live(&clip);
        let max_len = (MAX_PIECE_S * SAMPLE_RATE as f32) as usize;
        assert_eq!(closed.len(), 2);
        assert!(closed.iter().all(|piece| piece.len() <= max_len));
        assert_eq!(joined(&closed, &rest), clip);
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

//! Voice activity, measured exactly as V1 does: WebRTC VAD at aggressiveness 2
//! on 30 ms frames.

use webrtc_vad::{SampleRate, Vad, VadMode};

use crate::audio::{to_i16, SAMPLE_RATE};

const FRAME_MS: usize = 30;
const FRAME_SAMPLES: usize = SAMPLE_RATE as usize * FRAME_MS / 1000;
const FRAME_S: f32 = FRAME_MS as f32 / 1000.0;

/// Below this many seconds of voiced frames a clip is non-speech. V1 measured
/// at most 0.12 s on 125 noise realizations and at least 0.33 s on the
/// shortest real word ("non").
pub const MIN_SPEECH_DURATION_S: f32 = 0.20;

/// Margin kept around the voiced span when trimming. V1: silence around a
/// lone word makes Parakeet return nothing (12/15 recognized with 0.6 s of
/// tail, 3-5/15 with 10 s; trimmed, 10-12/15 whatever the tail).
pub const TRIM_MARGIN_S: f32 = 0.3;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SpeechSpan {
    /// Start of the first voiced frame, in seconds.
    pub first_s: f32,
    /// End of the last voiced frame, in seconds.
    pub last_s: f32,
    /// Total voiced seconds.
    pub voiced_s: f32,
}

impl SpeechSpan {
    pub fn carries_speech(&self) -> bool {
        self.voiced_s >= MIN_SPEECH_DURATION_S
    }
}

/// Per-frame voiced flags (30 ms frames; a trailing partial frame is ignored).
pub fn voiced_frames(samples: &[f32]) -> Vec<bool> {
    // A Vad holds a raw C pointer and is not Send: one per call, it is cheap.
    let mut vad = Vad::new_with_rate_and_mode(SampleRate::Rate16kHz, VadMode::Aggressive);
    samples
        .as_chunks::<FRAME_SAMPLES>()
        .0
        .iter()
        .map(|frame| {
            let pcm: Vec<i16> = frame.iter().map(|&s| to_i16(s)).collect();
            // A 30 ms frame at 16 kHz is always a valid length; treat a refusal as non-speech.
            vad.is_voice_segment(&pcm).unwrap_or(false)
        })
        .collect()
}

pub fn speech_span(samples: &[f32]) -> SpeechSpan {
    let frames = voiced_frames(samples);
    let first = frames.iter().position(|&voiced| voiced);
    let last = frames.iter().rposition(|&voiced| voiced);
    match (first, last) {
        (Some(first), Some(last)) => SpeechSpan {
            first_s: first as f32 * FRAME_S,
            last_s: (last + 1) as f32 * FRAME_S,
            voiced_s: frames.iter().filter(|&&voiced| voiced).count() as f32 * FRAME_S,
        },
        _ => SpeechSpan {
            first_s: 0.0,
            last_s: 0.0,
            voiced_s: 0.0,
        },
    }
}

/// The voiced span plus `TRIM_MARGIN_S` on each side; internal silences are kept.
pub fn trimmed_to_speech<'a>(samples: &'a [f32], span: &SpeechSpan) -> &'a [f32] {
    if span.voiced_s <= 0.0 {
        return samples;
    }
    let rate = SAMPLE_RATE as f32;
    let start = ((span.first_s - TRIM_MARGIN_S).max(0.0) * rate) as usize;
    let end = (((span.last_s + TRIM_MARGIN_S) * rate) as usize).min(samples.len());
    &samples[start.min(end)..end]
}

/// Seconds per VAD frame, for callers that walk `voiced_frames`.
pub fn frame_seconds() -> f32 {
    FRAME_S
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Harmonic stack: reads as voiced to WebRTC VAD, like V1's `_voiced_block`.
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

    #[test]
    fn silence_has_no_speech() {
        let span = speech_span(&vec![0.0; SAMPLE_RATE as usize]);
        assert_eq!(span.voiced_s, 0.0);
        assert!(!span.carries_speech());
    }

    #[test]
    fn trimming_cuts_the_silent_ends_only() {
        let mut clip = vec![0.0; 2 * SAMPLE_RATE as usize];
        clip.extend(voiced(1.0));
        clip.extend(vec![0.0; 3 * SAMPLE_RATE as usize]);
        let span = speech_span(&clip);
        assert!(span.carries_speech(), "{span:?}");
        assert!((span.first_s - 2.0).abs() < 0.1, "{span:?}");
        let trimmed = trimmed_to_speech(&clip, &span);
        let trimmed_s = trimmed.len() as f32 / SAMPLE_RATE as f32;
        assert!((trimmed_s - (span.last_s - span.first_s + 2.0 * TRIM_MARGIN_S)).abs() < 0.01);
    }
}

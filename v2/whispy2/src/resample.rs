//! Device audio → the 16 kHz mono the pipeline takes.
//!
//! Microphones on a Mac run at 44.1 or 48 kHz; V1 let PortAudio convert.
//! Here: average the channels, then band-limited (windowed-sinc) interpolation
//! with the cut-off just under the 8 kHz Nyquist of the output, so content
//! above it is filtered out instead of folding back onto speech.

use whispy_core::audio::SAMPLE_RATE;

/// Half-width of the sinc kernel, in input samples (scaled by the ratio when downsampling).
const KERNEL_HALF_WIDTH: f64 = 16.0;
/// Cut-off as a fraction of the output Nyquist, leaving room for the window's slope.
const CUTOFF: f64 = 0.92;

pub fn to_16k_mono(interleaved: &[f32], channels: usize, rate: u32) -> Vec<f32> {
    let mono = downmix(interleaved, channels);
    if rate == SAMPLE_RATE {
        return mono;
    }
    resample(&mono, rate, SAMPLE_RATE)
}

fn downmix(interleaved: &[f32], channels: usize) -> Vec<f32> {
    if channels <= 1 {
        return interleaved.to_vec();
    }
    interleaved
        .chunks_exact(channels)
        .map(|frame| frame.iter().sum::<f32>() / channels as f32)
        .collect()
}

fn resample(input: &[f32], from: u32, to: u32) -> Vec<f32> {
    let step = from as f64 / to as f64;
    // Downsampling widens the kernel and lowers the cut-off to the output's Nyquist.
    let scale = step.max(1.0);
    let cutoff = CUTOFF / scale;
    let half_width = KERNEL_HALF_WIDTH * scale;
    let output_len = (input.len() as f64 / step).floor() as usize;
    (0..output_len)
        .map(|index| {
            let center = index as f64 * step;
            let first = (center - half_width).ceil().max(0.0) as usize;
            let last = ((center + half_width).floor() as usize).min(input.len() - 1);
            let mut sum = 0.0;
            for (offset, sample) in input[first..=last].iter().enumerate() {
                let distance = (first + offset) as f64 - center;
                sum +=
                    *sample as f64 * cutoff * sinc(distance * cutoff) * hann(distance / half_width);
            }
            sum as f32
        })
        .collect()
}

fn sinc(x: f64) -> f64 {
    if x.abs() < 1e-9 {
        return 1.0;
    }
    let angle = std::f64::consts::PI * x;
    angle.sin() / angle
}

/// Hann window over -1..1.
fn hann(position: f64) -> f64 {
    if position.abs() >= 1.0 {
        return 0.0;
    }
    0.5 * (1.0 + (std::f64::consts::PI * position).cos())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(frequency: f64, rate: u32, seconds: f64) -> Vec<f32> {
        let count = (rate as f64 * seconds) as usize;
        (0..count)
            .map(|index| {
                (0.5 * (2.0 * std::f64::consts::PI * frequency * index as f64 / rate as f64).sin())
                    as f32
            })
            .collect()
    }

    /// RMS away from the edges, where the kernel runs out of input.
    fn middle_rms(samples: &[f32]) -> f32 {
        let middle = &samples[samples.len() / 4..samples.len() * 3 / 4];
        (middle.iter().map(|sample| sample * sample).sum::<f32>() / middle.len() as f32).sqrt()
    }

    #[test]
    fn speech_band_tones_keep_their_level_from_48k_and_44k1() {
        for rate in [48_000, 44_100] {
            let output = to_16k_mono(&tone(1_000.0, rate, 1.0), 1, rate);
            assert!(
                (output.len() as i64 - 16_000).abs() <= 1,
                "{rate}: {}",
                output.len()
            );
            let level = middle_rms(&output);
            assert!((level - 0.3536).abs() < 0.01, "{rate}: rms {level}");
        }
    }

    #[test]
    fn content_above_8k_does_not_fold_back() {
        // 12 kHz would alias to 4 kHz, in the middle of speech, without a filter.
        let output = to_16k_mono(&tone(12_000.0, 48_000, 1.0), 1, 48_000);
        assert!(middle_rms(&output) < 0.01, "rms {}", middle_rms(&output));
    }

    #[test]
    fn stereo_is_averaged() {
        let interleaved = [0.25, 0.75, -0.5, 0.0];
        assert_eq!(to_16k_mono(&interleaved, 2, SAMPLE_RATE), vec![0.5, -0.25]);
    }

    #[test]
    fn empty_input_gives_empty_output() {
        assert!(to_16k_mono(&[], 1, 48_000).is_empty());
    }
}

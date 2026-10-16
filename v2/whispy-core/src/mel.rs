//! NeMo log-mel features (128 bins), as Parakeet was trained on.
//!
//! A port of `NemoPreprocessorNumpy` from onnx-asr, the preprocessor V1 runs
//! on the CPU provider: pre-emphasis 0.97, 512-point FFT of a 400-sample Hann
//! window every 160 samples, Slaney mel filterbank, log with a 2^-24 guard,
//! then per-bin normalization over the clip.

use rustfft::{num_complex::Complex, FftPlanner};

pub const MEL_BINS: usize = 128;
const N_FFT: usize = 512;
const WIN_LENGTH: usize = 400;
const HOP_LENGTH: usize = 160;
const SPECTRUM_BINS: usize = N_FFT / 2 + 1;
const PREEMPHASIS: f32 = 0.97;
const LOG_ZERO_GUARD: f32 = 1.0 / 16_777_216.0; // 2^-24
const SAMPLE_RATE_HZ: f64 = 16_000.0;

/// Features in `[MEL_BINS][frames]` row-major order, ready for an
/// `audio_signal` tensor of shape `[1, MEL_BINS, frames]`, and the number of
/// valid frames (the encoder's `length`).
pub struct Features {
    pub data: Vec<f32>,
    pub frames: usize,
    pub valid_frames: usize,
}

pub struct MelExtractor {
    filterbank: Vec<[f32; MEL_BINS]>, // one row per spectrum bin
    window: [f64; N_FFT],
    planner: FftPlanner<f64>,
}

impl Default for MelExtractor {
    fn default() -> Self {
        Self::new()
    }
}

impl MelExtractor {
    pub fn new() -> Self {
        MelExtractor {
            filterbank: slaney_filterbank(),
            window: padded_hann_window(),
            planner: FftPlanner::new(),
        }
    }

    /// `None` when the clip is too short to normalize (under two hops).
    pub fn features(&mut self, samples: &[f32]) -> Option<Features> {
        let valid_frames = samples.len() / HOP_LENGTH;
        if valid_frames < 2 {
            return None;
        }
        let half = N_FFT / 2;
        let mut padded = vec![0.0f32; samples.len() + N_FFT];
        for (i, &sample) in samples.iter().enumerate() {
            let previous = if i == 0 { 0.0 } else { samples[i - 1] };
            padded[half + i] = sample - PREEMPHASIS * previous;
        }
        let frames = (padded.len() - N_FFT) / HOP_LENGTH + 1;

        let fft = self.planner.plan_fft_forward(N_FFT);
        let mut log_mel = vec![0.0f32; MEL_BINS * frames];
        let mut buffer = vec![Complex::new(0.0f64, 0.0); N_FFT];
        for frame in 0..frames {
            let offset = frame * HOP_LENGTH;
            for (k, slot) in buffer.iter_mut().enumerate() {
                *slot = Complex::new(padded[offset + k] as f64 * self.window[k], 0.0);
            }
            fft.process(&mut buffer);
            let mut mel = [0.0f32; MEL_BINS];
            for (bin, value) in buffer.iter().take(SPECTRUM_BINS).enumerate() {
                let power = (value.norm() as f32).powi(2);
                if power == 0.0 {
                    continue;
                }
                for (m, weight) in self.filterbank[bin].iter().enumerate() {
                    mel[m] += power * weight;
                }
            }
            for (m, energy) in mel.iter().enumerate() {
                log_mel[m * frames + frame] = (energy + LOG_ZERO_GUARD).ln();
            }
        }

        for m in 0..MEL_BINS {
            let row = &mut log_mel[m * frames..(m + 1) * frames];
            let mean =
                row[..valid_frames].iter().map(|&v| v as f64).sum::<f64>() / valid_frames as f64;
            let variance = row[..valid_frames]
                .iter()
                .map(|&v| (v as f64 - mean).powi(2))
                .sum::<f64>()
                / (valid_frames - 1) as f64;
            let scale = variance.sqrt() + 1e-5;
            for (frame, value) in row.iter_mut().enumerate() {
                *value = if frame < valid_frames {
                    ((*value as f64 - mean) / scale) as f32
                } else {
                    0.0
                };
            }
        }
        Some(Features {
            data: log_mel,
            frames,
            valid_frames,
        })
    }
}

/// `np.hanning(400)` (symmetric) centered in 512 samples.
fn padded_hann_window() -> [f64; N_FFT] {
    let mut window = [0.0f64; N_FFT];
    let offset = (N_FFT - WIN_LENGTH) / 2;
    for k in 0..WIN_LENGTH {
        let phase = 2.0 * std::f64::consts::PI * k as f64 / (WIN_LENGTH - 1) as f64;
        window[offset + k] = 0.5 - 0.5 * phase.cos();
    }
    window
}

fn hz_to_mel(hz: f64) -> f64 {
    let f_sp = 200.0 / 3.0;
    let log_step = 6.4f64.ln() / 27.0;
    if hz < 1000.0 {
        hz / f_sp
    } else {
        15.0 + (hz / 1000.0).ln() / log_step
    }
}

fn mel_to_hz(mel: f64) -> f64 {
    let f_sp = 200.0 / 3.0;
    let log_step = 6.4f64.ln() / 27.0;
    if mel < 15.0 {
        mel * f_sp
    } else {
        1000.0 * (log_step * (mel - 15.0)).exp()
    }
}

/// `librosa.filters.mel(sr=16000, n_fft=512, n_mels=128, norm="slaney")`, transposed.
fn slaney_filterbank() -> Vec<[f32; MEL_BINS]> {
    let max_mel = hz_to_mel(SAMPLE_RATE_HZ / 2.0);
    let mel_points: Vec<f64> = (0..MEL_BINS + 2)
        .map(|i| mel_to_hz(max_mel * i as f64 / (MEL_BINS + 1) as f64))
        .collect();
    let mut filterbank = vec![[0.0f32; MEL_BINS]; SPECTRUM_BINS];
    for (bin, row) in filterbank.iter_mut().enumerate() {
        let frequency = SAMPLE_RATE_HZ / 2.0 * bin as f64 / (SPECTRUM_BINS - 1) as f64;
        for (m, weight) in row.iter_mut().enumerate() {
            let lower = (frequency - mel_points[m]) / (mel_points[m + 1] - mel_points[m]);
            let upper = (mel_points[m + 2] - frequency) / (mel_points[m + 2] - mel_points[m + 1]);
            let normalization = 2.0 / (mel_points[m + 2] - mel_points[m]);
            *weight = (lower.min(upper).max(0.0) * normalization) as f32;
        }
    }
    filterbank
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn filterbank_matches_the_one_onnx_asr_ships() {
        // Reference values read from onnx_asr/preprocessors/data/fbanks.npz["nemo128"] (257 x 128).
        let filterbank = slaney_filterbank();
        let total: f32 = filterbank.iter().flat_map(|row| row.iter()).sum();
        assert!((total - 4.0904875).abs() < 1e-4, "total {total}");
        let first_column: Vec<(usize, f32)> = filterbank
            .iter()
            .enumerate()
            .filter(|(_, row)| row[0] > 0.0)
            .map(|(bin, row)| (bin, row[0]))
            .collect();
        assert_eq!(first_column.len(), 1);
        assert_eq!(first_column[0].0, 1);
        assert!((first_column[0].1 - 0.02837754).abs() < 1e-6);
        let last_column: f32 = filterbank.iter().map(|row| row[MEL_BINS - 1]).sum();
        assert!((last_column - 0.031943686).abs() < 1e-6);
        let max = filterbank
            .iter()
            .flat_map(|row| row.iter())
            .fold(0.0f32, |a, &b| a.max(b));
        assert!((max - 0.042366076).abs() < 1e-6);
    }

    #[test]
    fn features_are_normalized_over_valid_frames() {
        let samples: Vec<f32> = (0..16_000).map(|i| (i as f32 * 0.05).sin() * 0.1).collect();
        let features = MelExtractor::new().features(&samples).unwrap();
        assert_eq!(features.valid_frames, 100);
        assert_eq!(features.frames, 101);
        let row = &features.data[..features.frames];
        let mean: f32 = row[..100].iter().sum::<f32>() / 100.0;
        assert!(mean.abs() < 1e-3, "mean {mean}");
        assert_eq!(row[100], 0.0);
    }

    #[test]
    fn too_short_clips_have_no_features() {
        assert!(MelExtractor::new().features(&[0.0; 200]).is_none());
    }
}

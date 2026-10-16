//! PCM helpers and the two gates V1 calibrated on real dictation.
//!
//! Samples are 16 kHz mono `f32` in -1.0..1.0 everywhere in this crate.

use std::path::Path;

use crate::Error;

pub const SAMPLE_RATE: u32 = 16_000;

/// Below this loudest-window RMS a clip is silence and never reaches an engine.
/// V1 measured fillers ("Yeah.", "Thank you.") up to 0.00065 on silence and
/// room noise, real speech from 0.01 (quiet) to 0.15 (normal).
pub const SILENCE_RMS_THRESHOLD: f32 = 0.005;

/// The silence gate looks at the loudest window of this length, so one word
/// in a long key-hold is not averaged away (V1, PEAK_RMS_WINDOW_S).
pub const PEAK_RMS_WINDOW_S: f32 = 0.5;

/// Quiet clips are scaled up to this whole-clip RMS before the engine sees
/// them. V1 (lost-speech-probe, 2026-10-09): the real lost dictations sat at
/// RMS 0.010-0.013 and all came back as the right sentence at 0.05; 0.1 made
/// one noise clip say "Uh".
pub const LOUDNESS_TARGET_RMS: f32 = 0.05;

pub fn seconds(samples: &[f32]) -> f32 {
    samples.len() as f32 / SAMPLE_RATE as f32
}

/// Reads a 16 kHz mono 16-bit PCM WAV, the format V1 records and keeps.
pub fn read_wav(path: &Path) -> Result<Vec<f32>, Error> {
    let mut reader = hound::WavReader::open(path)
        .map_err(|error| Error::UnsupportedAudio(format!("{}: {error}", path.display())))?;
    let spec = reader.spec();
    let is_expected_format = spec.channels == 1
        && spec.sample_rate == SAMPLE_RATE
        && spec.bits_per_sample == 16
        && spec.sample_format == hound::SampleFormat::Int;
    if !is_expected_format {
        return Err(Error::UnsupportedAudio(format!(
            "{}: {} channel(s), {} Hz, {} bits {:?}; expected 1 channel, 16000 Hz, 16 bits Int",
            path.display(),
            spec.channels,
            spec.sample_rate,
            spec.bits_per_sample,
            spec.sample_format
        )));
    }
    reader
        .samples::<i16>()
        .map(|sample| sample.map(|value| value as f32 / 32768.0))
        .collect::<Result<Vec<f32>, _>>()
        .map_err(|error| Error::UnsupportedAudio(format!("{}: {error}", path.display())))
}

/// Writes samples as a 16 kHz mono 16-bit PCM WAV.
pub fn write_wav(path: &Path, samples: &[f32]) -> Result<(), Error> {
    let spec = hound::WavSpec {
        channels: 1,
        sample_rate: SAMPLE_RATE,
        bits_per_sample: 16,
        sample_format: hound::SampleFormat::Int,
    };
    let to_io = |error: hound::Error| {
        Error::Io(std::io::Error::other(format!(
            "{}: {error}",
            path.display()
        )))
    };
    let mut writer = hound::WavWriter::create(path, spec).map_err(to_io)?;
    for &sample in samples {
        writer.write_sample(to_i16(sample)).map_err(to_io)?;
    }
    writer.finalize().map_err(to_io)
}

pub fn to_i16(sample: f32) -> i16 {
    (sample * 32768.0).round().clamp(-32768.0, 32767.0) as i16
}

/// Whole-clip RMS after removing the DC offset.
pub fn rms(samples: &[f32]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let mean = samples.iter().map(|&s| s as f64).sum::<f64>() / samples.len() as f64;
    let power = samples
        .iter()
        .map(|&s| (s as f64 - mean).powi(2))
        .sum::<f64>()
        / samples.len() as f64;
    power.sqrt() as f32
}

/// Highest RMS over any `PEAK_RMS_WINDOW_S` window (hop of a fifth of a
/// window); a clip shorter than one window is measured whole.
pub fn peak_rms(samples: &[f32]) -> f32 {
    let window = (PEAK_RMS_WINDOW_S * SAMPLE_RATE as f32) as usize;
    if samples.len() <= window {
        let power =
            samples.iter().map(|&s| (s as f64).powi(2)).sum::<f64>() / samples.len().max(1) as f64;
        return power.sqrt() as f32;
    }
    let mut cumulative = Vec::with_capacity(samples.len() + 1);
    cumulative.push(0.0f64);
    for &sample in samples {
        let last = *cumulative.last().unwrap_or(&0.0);
        cumulative.push(last + (sample as f64).powi(2));
    }
    let hop = (window / 5).max(1);
    let loudest = (0..=samples.len() - window)
        .step_by(hop)
        .map(|start| (cumulative[start + window] - cumulative[start]) / window as f64)
        .fold(0.0f64, f64::max);
    loudest.sqrt() as f32
}

/// A copy scaled to `target` RMS (DC removed, clipped), or `None` when the
/// clip is already at least that loud or is digital silence.
pub fn louder_copy(samples: &[f32], target: f32) -> Option<Vec<f32>> {
    let level = rms(samples);
    if level == 0.0 || level >= target {
        return None;
    }
    let mean = samples.iter().sum::<f32>() / samples.len() as f32;
    let gain = target / level;
    Some(
        samples
            .iter()
            .map(|&s| ((s - mean) * gain).clamp(-1.0, 1.0))
            .collect(),
    )
}

/// `samples` with `lead_s` of silence before and `tail_s` after.
pub fn padded(samples: &[f32], lead_s: f32, tail_s: f32) -> Vec<f32> {
    let lead = (lead_s * SAMPLE_RATE as f32) as usize;
    let tail = (tail_s * SAMPLE_RATE as f32) as usize;
    let mut out = vec![0.0; lead];
    out.extend_from_slice(samples);
    out.resize(lead + samples.len() + tail, 0.0);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(seconds: f32, amplitude: f32) -> Vec<f32> {
        let count = (seconds * SAMPLE_RATE as f32) as usize;
        (0..count)
            .map(|i| {
                amplitude
                    * (i as f32 * 2.0 * std::f32::consts::PI * 220.0 / SAMPLE_RATE as f32).sin()
            })
            .collect()
    }

    #[test]
    fn peak_rms_finds_one_word_in_a_long_silence() {
        let mut clip = vec![0.0; 10 * SAMPLE_RATE as usize];
        clip.extend(tone(0.5, 0.1));
        // The whole-clip mean dilutes the word under the gate; the peak window does not.
        assert!(rms(&clip) < SILENCE_RMS_THRESHOLD * 5.0);
        assert!((peak_rms(&clip) - 0.1 / 2f32.sqrt()).abs() < 0.005);
    }

    #[test]
    fn louder_copy_reaches_the_target_and_skips_loud_clips() {
        let quiet = tone(1.0, 0.014);
        let louder = louder_copy(&quiet, LOUDNESS_TARGET_RMS).expect("a quiet clip is scaled");
        assert!((rms(&louder) - LOUDNESS_TARGET_RMS).abs() < 0.001);
        assert!(louder_copy(&tone(1.0, 0.5), LOUDNESS_TARGET_RMS).is_none());
        assert!(louder_copy(&vec![0.0; 100], LOUDNESS_TARGET_RMS).is_none());
    }

    #[test]
    fn padded_adds_silence_on_both_sides() {
        let out = padded(&[0.5, 0.5], 0.001, 0.002);
        assert_eq!(out.len(), 16 + 2 + 32);
        assert_eq!(out[16], 0.5);
        assert_eq!(out[0], 0.0);
        assert_eq!(*out.last().unwrap(), 0.0);
    }

    #[test]
    fn wav_round_trip_keeps_samples() {
        let path =
            std::env::temp_dir().join(format!("whispy-core-test-{}.wav", std::process::id()));
        let samples = vec![0.0, 0.25, -0.5, 0.999];
        write_wav(&path, &samples).unwrap();
        let back = read_wav(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        for (a, b) in samples.iter().zip(&back) {
            assert!((a - b).abs() < 1.0 / 16000.0);
        }
    }
}

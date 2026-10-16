//! whisper small through whisper.cpp (`ggml-small.bin`).

use std::path::Path;

use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperState,
};

use crate::audio::{padded, SAMPLE_RATE};
use crate::{Error, Transcriber};

/// whisper.cpp refuses input under one second ("input is too short"), so a
/// shorter clip gets trailing silence up to this length.
const MIN_INPUT_S: f32 = 1.1;

/// A segment is dropped when whisper itself doubts it. Measured on the lost
/// clips (2026-10-16): the real dictations (card whispy #2's "à améliorer, je
/// pense" and another short French one) read no-speech 0.07-0.09 and mean log probability -0.41 to
/// -0.80; the fillers and noise readings read no-speech 0.91 ("Thank you.") or
/// mean log probability -3.6 to -7.8.
const MAX_NO_SPEECH_PROBABILITY: f32 = 0.6;
const MIN_MEAN_LOG_PROBABILITY: f32 = -1.0;

/// Whisper also answers noise in scripts the user never dictates (Georgian,
/// Khmer, Hangul...) with a high confidence. Whispy's users dictate in Latin
/// script; ponytail: a letter outside it drops the segment. The ceiling is
/// Cyrillic or Greek dictation, which Parakeet covers; the upgrade is a
/// per-user list of scripts.
fn is_latin_script(text: &str) -> bool {
    text.chars()
        .filter(|c| c.is_alphabetic())
        .all(|c| (c as u32) < 0x0250 || (0x1E00..=0x1EFF).contains(&(c as u32)))
}

fn mean_text_token_log_probability(segment: &whisper_rs::WhisperSegment<'_>) -> f32 {
    let mut total = 0.0f32;
    let mut count = 0;
    for index in 0..segment.n_tokens() {
        let Some(token) = segment.get_token(index) else {
            continue;
        };
        let is_special = token
            .to_str_lossy()
            .map(|text| text.starts_with("[_") || text.starts_with("<|"))
            .unwrap_or(true);
        if !is_special {
            total += token.token_data().plog;
            count += 1;
        }
    }
    if count == 0 {
        f32::NEG_INFINITY
    } else {
        total / count as f32
    }
}

pub struct Whisper {
    // The state borrows nothing but keeps the context alive through an Arc;
    // the context is kept too so the engine owns everything it uses.
    _context: WhisperContext,
    state: WhisperState,
    threads: i32,
}

impl Whisper {
    pub fn load(model: &Path) -> Result<Self, Error> {
        whisper_rs::install_logging_hooks();
        // Metal on (the `metal` feature): ~0.5 s per clip against ~1.2 s on
        // CPU, same footprint (~720 MB for a 180 s dictation either way).
        let context = WhisperContext::new_with_params(model, WhisperContextParameters::default())
            .map_err(|error| {
            Error::Inference(format!("loading {}: {error}", model.display()))
        })?;
        let state = context
            .create_state()
            .map_err(|error| Error::Inference(format!("whisper state: {error}")))?;
        let threads = std::thread::available_parallelism()
            .map(|n| n.get().min(8) as i32)
            .unwrap_or(4);
        Ok(Whisper {
            _context: context,
            state,
            threads,
        })
    }
}

impl Transcriber for Whisper {
    fn name(&self) -> &'static str {
        "whisper"
    }

    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
        let minimum = (MIN_INPUT_S * SAMPLE_RATE as f32) as usize;
        let input = if samples.len() < minimum {
            let missing_s = (minimum - samples.len()) as f32 / SAMPLE_RATE as f32;
            padded(samples, 0.0, missing_s)
        } else {
            samples.to_vec()
        };
        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        // Detected, never forced: a forced language made V1's Whisper
        // translate instead of transcribe.
        params.set_language(Some("auto"));
        params.set_n_threads(self.threads);
        params.set_no_context(true);
        // No temperature fallback: it resamples a doubtful clip at random and
        // turned noise into different garbage on every run.
        params.set_temperature_inc(0.0);
        params.set_no_timestamps(true);
        params.set_suppress_blank(true);
        params.set_suppress_nst(true);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_special(false);
        params.set_print_timestamps(false);
        self.state
            .full(params, &input)
            .map_err(|error| Error::Inference(format!("whisper: {error}")))?;
        let mut text = String::new();
        for index in 0..self.state.full_n_segments() {
            let Some(segment) = self.state.get_segment(index) else {
                continue;
            };
            let mean_log_probability = mean_text_token_log_probability(&segment);
            if std::env::var_os("WHISPY_DEBUG_WHISPER").is_some() {
                eprintln!(
                    "whisper segment: no_speech {:.2}, mean logprob {:.2}: {:?}",
                    segment.no_speech_probability(),
                    mean_log_probability,
                    segment.to_str_lossy().unwrap_or_default()
                );
            }
            let piece = segment
                .to_str_lossy()
                .map_err(|error| Error::Inference(format!("whisper segment: {error}")))?;
            let is_confident = segment.no_speech_probability() <= MAX_NO_SPEECH_PROBABILITY
                && mean_log_probability >= MIN_MEAN_LOG_PROBABILITY;
            if is_confident && is_latin_script(&piece) {
                text.push_str(&piece);
            }
        }
        Ok(text.trim().to_string())
    }
}

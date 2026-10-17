//! Running the engines on the clips, and the numbers drawn from the runs.

use std::collections::HashMap;
use std::time::Instant;

use whispy_core::pipeline::{DEFAULT_ENGINE, DEFAULT_FALLBACK, DEFAULT_STRATEGY};
use whispy_core::{EngineKind, Strategy};

use crate::corpus::{Clip, Group, Kind};
use crate::oracle::{Labels, Recovery};
use crate::wer;

/// Each ~5 s reference sentence is transcribed this many times, so the p95
/// of criterion 4 rests on more than one draw per clip.
const SENTENCE_REPEATS: usize = 5;

pub fn repeats(clip: &Clip) -> usize {
    if clip.group == Group::Reference && clip.kind == Kind::Sentence {
        SENTENCE_REPEATS
    } else {
        1
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Config {
    pub primary: EngineKind,
    pub fallback: Option<EngineKind>,
    pub strategy: Strategy,
}

impl Config {
    pub fn library_default() -> Self {
        Config {
            primary: DEFAULT_ENGINE,
            fallback: DEFAULT_FALLBACK,
            strategy: DEFAULT_STRATEGY,
        }
    }

    pub fn label(&self) -> String {
        match self.fallback {
            Some(fallback) => format!(
                "{} then {} / {}",
                self.primary.name(),
                fallback.name(),
                self.strategy.name()
            ),
            None => format!("{} / {}", self.primary.name(), self.strategy.name()),
        }
    }

    /// Every single-engine configuration, then every fallback pair.
    pub fn all() -> Vec<Config> {
        let mut configs = Vec::new();
        for fallback_pairs in [false, true] {
            for primary in EngineKind::ALL {
                for strategy in Strategy::ALL {
                    let fallback = fallback_pairs.then(|| other(primary));
                    configs.push(Config {
                        primary,
                        fallback,
                        strategy,
                    });
                }
            }
        }
        configs
    }
}

fn other(engine: EngineKind) -> EngineKind {
    match engine {
        EngineKind::Parakeet => EngineKind::Whisper,
        EngineKind::Whisper => EngineKind::Parakeet,
    }
}

/// What one clip gave: its text and the time of each repetition.
#[derive(Clone, Debug, Default)]
pub struct Measured {
    pub text: String,
    pub seconds: Vec<f64>,
}

/// Results per (engine, strategy), in clip order.
pub type Runs = HashMap<(EngineKind, Strategy), Vec<Measured>>;

pub fn run_engines(clips: &[Clip]) -> Result<Runs, String> {
    let mut runs = Runs::new();
    for engine_kind in EngineKind::ALL {
        let started = Instant::now();
        let mut engine = engine_kind.load().map_err(|error| error.to_string())?;
        eprintln!(
            "banc: {} loaded in {:.1} s",
            engine_kind.name(),
            started.elapsed().as_secs_f64()
        );
        // Warm-up: the first call pays one-off allocations, not dictation latency.
        if let Some(clip) = clips.iter().find(|clip| clip.group == Group::Reference) {
            engine
                .transcribe(&clip.samples)
                .map_err(|error| error.to_string())?;
        }
        for strategy in Strategy::ALL {
            eprintln!("banc: {} / {}", engine_kind.name(), strategy.name());
            let mut measured = Vec::with_capacity(clips.len());
            for clip in clips {
                let mut result = Measured::default();
                for repetition in 0..repeats(clip) {
                    let started = Instant::now();
                    let text = match strategy.prepare(&clip.samples) {
                        Some(input) => engine
                            .transcribe(&input)
                            .map_err(|error| format!("{}: {error}", clip.id))?,
                        None => String::new(),
                    };
                    result.seconds.push(started.elapsed().as_secs_f64());
                    if repetition == 0 {
                        result.text = text;
                    }
                }
                measured.push(result);
            }
            runs.insert((engine_kind, strategy), measured);
        }
    }
    Ok(runs)
}

/// The outcome of `config` on clip `index`, derived from the per-engine runs:
/// the fallback answers (and its time adds up) only when the primary is empty.
pub fn outcome(runs: &Runs, config: &Config, index: usize) -> Measured {
    let primary = &runs[&(config.primary, config.strategy)][index];
    match config.fallback {
        Some(fallback) if primary.text.is_empty() => {
            let second = &runs[&(fallback, config.strategy)][index];
            Measured {
                text: second.text.clone(),
                seconds: primary
                    .seconds
                    .iter()
                    .zip(&second.seconds)
                    .map(|(a, b)| a + b)
                    .collect(),
            }
        }
        _ => primary.clone(),
    }
}

/// The numbers of one row of the report.
#[derive(Clone, Debug, Default)]
pub struct Metrics {
    non_empty: HashMap<&'static str, (usize, usize)>,
    word_errors: HashMap<&'static str, (usize, usize)>,
    /// Every speech clip's transcription time (lost, reference, quiet).
    pub latencies: Vec<f64>,
    /// The ~5 s reference sentences only (criterion 4).
    pub sentence_latencies: Vec<f64>,
    /// The lost clips that hold speech, per the oracle and the user's ear
    /// (criterion 3); zero clips when the oracle was not run.
    pub lost_speech: Recovery,
}

impl Metrics {
    pub fn from_outcomes(
        clips: &[Clip],
        labels: Option<&Labels>,
        outcome_of: impl Fn(usize) -> Measured,
    ) -> Self {
        let mut metrics = Metrics::default();
        for (index, clip) in clips.iter().enumerate() {
            let measured = outcome_of(index);
            if let (Group::Lost, Some(labels)) = (clip.group, labels) {
                metrics
                    .lost_speech
                    .add(labels.get(&clip.id), &measured.text);
            }
            let group = clip.group.name();
            let counts = metrics.non_empty.entry(group).or_default();
            counts.1 += 1;
            if !measured.text.trim().is_empty() {
                counts.0 += 1;
            }
            if let (Some(expected), true) = (
                &clip.expected,
                matches!(clip.group, Group::Reference | Group::Quiet),
            ) {
                let expected = wer::normalized_words(expected);
                let errors = wer::word_edits(&expected, &wer::normalized_words(&measured.text));
                let totals = metrics.word_errors.entry(group).or_default();
                totals.0 += errors;
                totals.1 += expected.len();
            }
            if clip.group != Group::NonSpeech {
                metrics.latencies.extend(&measured.seconds);
            }
            if clip.group == Group::Reference && clip.kind == Kind::Sentence {
                metrics.sentence_latencies.extend(&measured.seconds);
            }
        }
        metrics
    }

    /// (clips with text, clips) in `group`.
    pub fn non_empty(&self, group: Group) -> (usize, usize) {
        self.non_empty
            .get(group.name())
            .copied()
            .unwrap_or_default()
    }

    pub fn non_empty_rate(&self, group: Group) -> f64 {
        let (with_text, total) = self.non_empty(group);
        if total == 0 {
            0.0
        } else {
            with_text as f64 / total as f64
        }
    }

    /// Word error rate over all words of `group`.
    pub fn wer(&self, group: Group) -> f64 {
        let (errors, words) = self
            .word_errors
            .get(group.name())
            .copied()
            .unwrap_or_default();
        if words == 0 {
            0.0
        } else {
            errors as f64 / words as f64
        }
    }

    pub fn combined_wer(&self) -> f64 {
        let (errors, words) = [Group::Reference, Group::Quiet]
            .iter()
            .filter_map(|group| self.word_errors.get(group.name()))
            .fold((0, 0), |(e, w), (errors, words)| (e + errors, w + words));
        if words == 0 {
            0.0
        } else {
            errors as f64 / words as f64
        }
    }
}

/// Nearest-rank percentile; 0 for no samples.
pub fn percentile(samples: &[f64], percent: f64) -> f64 {
    if samples.is_empty() {
        return 0.0;
    }
    let mut sorted = samples.to_vec();
    sorted.sort_by(|a, b| a.total_cmp(b));
    let rank = ((percent / 100.0) * sorted.len() as f64).ceil().max(1.0) as usize;
    sorted[rank.min(sorted.len()) - 1]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn percentile_uses_nearest_rank() {
        let samples: Vec<f64> = (1..=20).map(f64::from).collect();
        assert_eq!(percentile(&samples, 50.0), 10.0);
        assert_eq!(percentile(&samples, 95.0), 19.0);
        assert_eq!(percentile(&[3.0], 95.0), 3.0);
        assert_eq!(percentile(&[], 95.0), 0.0);
    }

    #[test]
    fn every_engine_and_strategy_appears_alone_and_with_a_fallback() {
        let configs = Config::all();
        assert_eq!(configs.len(), 16);
        assert!(configs.contains(&Config::library_default()));
    }
}

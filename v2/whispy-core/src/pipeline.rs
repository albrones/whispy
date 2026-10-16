//! PCM to text: split, gate, prepare, transcribe, fall back.

use crate::audio::{self, LOUDNESS_TARGET_RMS, SILENCE_RMS_THRESHOLD};
use crate::parakeet::Parakeet;
use crate::split::{self, MAX_PIECE_S};
use crate::vad;
use crate::whisper::Whisper;
use crate::{models, Error, Transcriber};

/// The engine the app uses, chosen by the bench (v2/bench/REPORT.md).
pub const DEFAULT_ENGINE: EngineKind = EngineKind::Parakeet;
/// The engine tried when the default one returns nothing; `None` for no fallback.
pub const DEFAULT_FALLBACK: Option<EngineKind> = Some(EngineKind::Whisper);
/// How a clip is prepared before the engine sees it.
pub const DEFAULT_STRATEGY: Strategy = Strategy::Louder;

/// Clips shorter than this get silence around them under [`Strategy::Padded`].
pub const SHORT_CLIP_S: f32 = 3.0;
/// Silence added before and after a short clip under [`Strategy::Padded`].
pub const PAD_S: f32 = 0.5;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum EngineKind {
    Parakeet,
    Whisper,
}

impl EngineKind {
    pub const ALL: [EngineKind; 2] = [EngineKind::Parakeet, EngineKind::Whisper];

    pub fn name(self) -> &'static str {
        match self {
            EngineKind::Parakeet => "parakeet",
            EngineKind::Whisper => "whisper",
        }
    }

    /// Loads the engine from the model files already on the Mac (see [`models`]).
    pub fn load(self) -> Result<Box<dyn Transcriber>, Error> {
        Ok(match self {
            EngineKind::Parakeet => Box::new(Parakeet::load(&models::parakeet_dir()?)?),
            EngineKind::Whisper => Box::new(Whisper::load(&models::whisper_model()?)?),
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Strategy {
    /// The clip as captured, no gate, no change.
    Raw,
    /// V1's gates (near-silence, too little voice), then the clip cut to its
    /// voiced span plus a margin.
    Gated,
    /// `Gated`, and a quiet clip scaled up to `LOUDNESS_TARGET_RMS`.
    Louder,
    /// `Louder`, and a clip under `SHORT_CLIP_S` padded with `PAD_S` of
    /// silence on each side.
    Padded,
}

impl Strategy {
    pub const ALL: [Strategy; 4] = [
        Strategy::Raw,
        Strategy::Gated,
        Strategy::Louder,
        Strategy::Padded,
    ];

    pub fn name(self) -> &'static str {
        match self {
            Strategy::Raw => "raw",
            Strategy::Gated => "gated",
            Strategy::Louder => "louder",
            Strategy::Padded => "padded",
        }
    }

    /// The engine's input for one piece, or `None` when a gate drops it.
    pub fn prepare(self, piece: &[f32]) -> Option<Vec<f32>> {
        if self == Strategy::Raw {
            return Some(piece.to_vec());
        }
        if audio::peak_rms(piece) < SILENCE_RMS_THRESHOLD {
            return None;
        }
        let span = vad::speech_span(piece);
        if !span.carries_speech() {
            return None;
        }
        let trimmed = vad::trimmed_to_speech(piece, &span);
        if self == Strategy::Gated {
            return Some(trimmed.to_vec());
        }
        let louder =
            audio::louder_copy(trimmed, LOUDNESS_TARGET_RMS).unwrap_or_else(|| trimmed.to_vec());
        if self == Strategy::Padded && audio::seconds(&louder) < SHORT_CLIP_S {
            return Some(audio::padded(&louder, PAD_S, PAD_S));
        }
        Some(louder)
    }
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Transcript {
    /// Text to insert; empty when there was nothing to transcribe.
    pub text: String,
    /// Engine that produced the text, `None` when it is empty.
    pub engine: Option<&'static str>,
}

pub struct Pipeline {
    primary: Box<dyn Transcriber>,
    fallback: Option<Box<dyn Transcriber>>,
    strategy: Strategy,
}

impl Pipeline {
    pub fn new(
        primary: Box<dyn Transcriber>,
        fallback: Option<Box<dyn Transcriber>>,
        strategy: Strategy,
    ) -> Self {
        Pipeline {
            primary,
            fallback,
            strategy,
        }
    }

    /// The configuration the bench chose: `DEFAULT_ENGINE`, `DEFAULT_FALLBACK`, `DEFAULT_STRATEGY`.
    pub fn load_default() -> Result<Self, Error> {
        let fallback = DEFAULT_FALLBACK.map(EngineKind::load).transpose()?;
        Ok(Pipeline::new(
            DEFAULT_ENGINE.load()?,
            fallback,
            DEFAULT_STRATEGY,
        ))
    }

    /// Text for a whole dictation (16 kHz mono). Long audio is split into
    /// pieces of at most `MAX_PIECE_S`, so memory stays bounded.
    pub fn transcribe(&mut self, samples: &[f32]) -> Result<Transcript, Error> {
        let mut texts = Vec::new();
        let mut engine = None;
        for range in split::pieces(samples, MAX_PIECE_S) {
            let piece = self.transcribe_piece(&samples[range])?;
            if !piece.text.is_empty() {
                texts.push(piece.text);
                engine = engine.or(piece.engine);
            }
        }
        // ponytail: plain space join; a boundary-aware join (V1 streaming) is
        // the upgrade if pieces split sentences visibly.
        Ok(Transcript {
            text: texts.join(" "),
            engine,
        })
    }

    fn transcribe_piece(&mut self, piece: &[f32]) -> Result<Transcript, Error> {
        let Some(input) = self.strategy.prepare(piece) else {
            return Ok(Transcript::default());
        };
        let text = self.primary.transcribe(&input)?;
        if !text.is_empty() {
            return Ok(Transcript {
                text,
                engine: Some(self.primary.name()),
            });
        }
        match self.fallback.as_mut() {
            Some(fallback) => {
                let text = fallback.transcribe(&input)?;
                let engine = (!text.is_empty()).then(|| fallback.name());
                Ok(Transcript { text, engine })
            }
            None => Ok(Transcript::default()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Answers a fixed text, and records how long each input was.
    struct Scripted {
        answer: &'static str,
        seen_lengths: std::sync::Arc<std::sync::Mutex<Vec<usize>>>,
    }

    impl Transcriber for Scripted {
        fn name(&self) -> &'static str {
            if self.answer.is_empty() {
                "mute"
            } else {
                "scripted"
            }
        }
        fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
            self.seen_lengths.lock().unwrap().push(samples.len());
            Ok(self.answer.to_string())
        }
    }

    fn scripted(
        answer: &'static str,
    ) -> (
        Box<dyn Transcriber>,
        std::sync::Arc<std::sync::Mutex<Vec<usize>>>,
    ) {
        let seen = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        (
            Box::new(Scripted {
                answer,
                seen_lengths: seen.clone(),
            }),
            seen,
        )
    }

    fn voiced(seconds: f32, amplitude: f32) -> Vec<f32> {
        let count = (seconds * audio::SAMPLE_RATE as f32) as usize;
        (0..count)
            .map(|i| {
                let t = i as f32 / audio::SAMPLE_RATE as f32;
                (1..=10)
                    .map(|h| amplitude * (2.0 * std::f32::consts::PI * 150.0 * h as f32 * t).sin())
                    .sum::<f32>()
            })
            .collect()
    }

    #[test]
    fn silence_never_reaches_an_engine_once_gated() {
        let (engine, seen) = scripted("Thank you.");
        let mut pipeline = Pipeline::new(engine, None, Strategy::Gated);
        let transcript = pipeline.transcribe(&vec![0.0; 16_000]).unwrap();
        assert_eq!(transcript, Transcript::default());
        assert!(seen.lock().unwrap().is_empty());
    }

    #[test]
    fn raw_sends_the_clip_untouched() {
        let (engine, seen) = scripted("Thank you.");
        let mut pipeline = Pipeline::new(engine, None, Strategy::Raw);
        let transcript = pipeline.transcribe(&vec![0.0; 16_000]).unwrap();
        assert_eq!(transcript.text, "Thank you.");
        assert_eq!(*seen.lock().unwrap(), vec![16_000]);
    }

    #[test]
    fn the_fallback_answers_when_the_primary_is_empty() {
        let (primary, _) = scripted("");
        let (fallback, _) = scripted("à améliorer, je pense");
        let mut pipeline = Pipeline::new(primary, Some(fallback), Strategy::Louder);
        let mut clip = vec![0.0; 8_000];
        clip.extend(voiced(1.0, 0.012));
        let transcript = pipeline.transcribe(&clip).unwrap();
        assert_eq!(transcript.text, "à améliorer, je pense");
        assert_eq!(transcript.engine, Some("scripted"));
    }

    #[test]
    fn short_clips_are_padded_and_quiet_ones_made_louder() {
        let clip = voiced(1.0, 0.012);
        let prepared = Strategy::Padded.prepare(&clip).unwrap();
        let louder = Strategy::Louder.prepare(&clip).unwrap();
        assert_eq!(
            prepared.len(),
            louder.len() + 2 * (PAD_S * audio::SAMPLE_RATE as f32) as usize
        );
        assert!((audio::rms(&louder) - LOUDNESS_TARGET_RMS).abs() < 0.002);
    }

    #[test]
    fn a_long_dictation_is_split_into_bounded_calls() {
        let (engine, seen) = scripted("mot");
        let mut pipeline = Pipeline::new(engine, None, Strategy::Raw);
        let transcript = pipeline.transcribe(&voiced(65.0, 0.01)).unwrap();
        let max_len = (MAX_PIECE_S * audio::SAMPLE_RATE as f32) as usize;
        let lengths = seen.lock().unwrap().clone();
        assert!(lengths.len() >= 4, "{lengths:?}");
        assert!(lengths.iter().all(|&len| len <= max_len));
        assert_eq!(transcript.text.split(' ').count(), lengths.len());
    }
}

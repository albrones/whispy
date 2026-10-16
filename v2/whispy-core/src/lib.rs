//! Whispy V2 core: everything between captured PCM and the text to insert.
//!
//! The app (menu bar, Fn key, insertion) lives elsewhere and only needs
//! [`Pipeline`]: hand it 16 kHz mono `f32` samples, get text back.
//!
//! ```no_run
//! let mut pipeline = whispy_core::Pipeline::load_default()?;
//! let samples = whispy_core::audio::read_wav(std::path::Path::new("clip.wav"))?;
//! let transcript = pipeline.transcribe(&samples)?;
//! println!("{} (by {:?})", transcript.text, transcript.engine);
//! # Ok::<(), whispy_core::Error>(())
//! ```

pub mod audio;
pub mod mel;
pub mod models;
pub mod parakeet;
pub mod pipeline;
pub mod split;
pub mod vad;
pub mod whisper;

pub use pipeline::{EngineKind, Pipeline, Strategy, Transcript, DEFAULT_ENGINE, DEFAULT_STRATEGY};

use std::fmt;

/// Turns 16 kHz mono PCM into text. One call is one independent utterance.
///
/// `Send` so the app can own an engine on a worker thread.
pub trait Transcriber: Send {
    /// Short stable name, used in logs and in the bench report.
    fn name(&self) -> &'static str;
    /// Text for `samples` (16 kHz mono, -1.0..1.0); empty when the engine heard nothing.
    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error>;
}

#[derive(Debug)]
pub enum Error {
    /// A model file is missing; names the path looked at and how to provide it.
    ModelMissing(String),
    /// Audio in a format the pipeline does not take; names the actual and expected format.
    UnsupportedAudio(String),
    /// The inference runtime failed.
    Inference(String),
    Io(std::io::Error),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::ModelMissing(message) => write!(f, "model missing: {message}"),
            Error::UnsupportedAudio(message) => write!(f, "unsupported audio: {message}"),
            Error::Inference(message) => write!(f, "inference failed: {message}"),
            Error::Io(error) => write!(f, "I/O error: {error}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        Error::Io(error)
    }
}

impl From<ort::Error> for Error {
    fn from(error: ort::Error) -> Self {
        Error::Inference(format!("ONNX Runtime: {error}"))
    }
}

//! Where the model files are. Nothing is downloaded: V2 reuses the weights
//! already on the Mac and fails with the paths it looked at otherwise.

use std::env;
use std::path::{Path, PathBuf};

use crate::Error;

/// The Hugging Face repository V1 (onnx-asr) downloads Parakeet from.
const PARAKEET_REPOSITORY: &str = "models--istupakov--parakeet-tdt-0.6b-v3-onnx";
const PARAKEET_FILES: [&str; 3] = [
    "encoder-model.int8.onnx",
    "decoder_joint-model.int8.onnx",
    "vocab.txt",
];
const WHISPER_FILE: &str = "ggml-small.bin";

fn home() -> PathBuf {
    env::var_os("HOME").map(PathBuf::from).unwrap_or_default()
}

/// The Hugging Face hub cache, resolved like `huggingface_hub` does.
fn hub_cache() -> PathBuf {
    if let Some(cache) = env::var_os("HF_HUB_CACHE") {
        return PathBuf::from(cache);
    }
    if let Some(hf_home) = env::var_os("HF_HOME") {
        return PathBuf::from(hf_home).join("hub");
    }
    home().join(".cache/huggingface/hub")
}

/// Directory holding the int8 Parakeet TDT 0.6b v3 ONNX files:
/// `WHISPY_PARAKEET_DIR`, else the snapshot V1 already downloaded.
pub fn parakeet_dir() -> Result<PathBuf, Error> {
    if let Some(dir) = env::var_os("WHISPY_PARAKEET_DIR") {
        return checked_parakeet_dir(PathBuf::from(dir));
    }
    let repository = hub_cache().join(PARAKEET_REPOSITORY);
    let revision = std::fs::read_to_string(repository.join("refs/main")).map_err(|_| {
        Error::ModelMissing(format!(
            "no Parakeet snapshot under {} (run Whispy V1 once, or set WHISPY_PARAKEET_DIR to a directory holding {})",
            repository.display(),
            PARAKEET_FILES.join(", ")
        ))
    })?;
    checked_parakeet_dir(repository.join("snapshots").join(revision.trim()))
}

fn checked_parakeet_dir(dir: PathBuf) -> Result<PathBuf, Error> {
    match PARAKEET_FILES.iter().find(|file| !dir.join(file).is_file()) {
        Some(missing) => Err(Error::ModelMissing(format!(
            "{} has no {missing}",
            dir.display()
        ))),
        None => Ok(dir),
    }
}

/// whisper.cpp small model: `WHISPY_WHISPER_MODEL`, else `~/.whispy/models/`,
/// else `~/.jarvis/models/` where it already is on this Mac.
pub fn whisper_model() -> Result<PathBuf, Error> {
    if let Some(path) = env::var_os("WHISPY_WHISPER_MODEL") {
        return existing(PathBuf::from(path));
    }
    let candidates = [
        home().join(".whispy/models").join(WHISPER_FILE),
        home().join(".jarvis/models").join(WHISPER_FILE),
    ];
    candidates
        .iter()
        .find(|path| path.is_file())
        .cloned()
        .ok_or_else(|| {
            Error::ModelMissing(format!(
                "{WHISPER_FILE} not found at {} (set WHISPY_WHISPER_MODEL)",
                candidates
                    .iter()
                    .map(|path| path.display().to_string())
                    .collect::<Vec<_>>()
                    .join(" or ")
            ))
        })
}

fn existing(path: PathBuf) -> Result<PathBuf, Error> {
    if Path::new(&path).is_file() {
        Ok(path)
    } else {
        Err(Error::ModelMissing(format!(
            "{} does not exist",
            path.display()
        )))
    }
}

//! Where the model files are, and how the app fetches the missing ones.
//!
//! Looking a model up never downloads anything: the bench and the engines
//! fail with the paths they looked at. Only the app calls [`download_missing`]
//! before it loads, so a fresh install gets its models on first launch. Each
//! file comes from a pinned Hugging Face revision and is checked against its
//! SHA-256 before it is moved into place.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::Error;

/// The Hugging Face repository V1 (onnx-asr) downloads Parakeet from.
const PARAKEET_REPOSITORY: &str = "models--istupakov--parakeet-tdt-0.6b-v3-onnx";
const PARAKEET_FILES: [&str; 3] = [
    "encoder-model.int8.onnx",
    "decoder_joint-model.int8.onnx",
    "vocab.txt",
];
const WHISPER_FILE: &str = "ggml-small.bin";
/// Where the app puts the Parakeet files it downloads, under [`models_dir`].
const PARAKEET_DOWNLOAD_DIR: &str = "parakeet-tdt-0.6b-v3-int8";

/// Pinned sources: the revision V1 (onnx-asr) resolved, and whisper.cpp's.
const PARAKEET_URL: &str =
    "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce";
const WHISPER_URL: &str =
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1";
/// SHA-256 of each file at those revisions, in the order of [`PARAKEET_FILES`].
const PARAKEET_SHA256: [&str; 3] = [
    "6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09",
    "eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70",
    "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d",
];
const PARAKEET_BYTES: [u64; 3] = [652_183_999, 18_202_004, 93_939];
const WHISPER_SHA256: &str = "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b";
const WHISPER_BYTES: u64 = 487_601_967;

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

/// `~/.whispy/models`: where the app keeps the models it downloads.
pub fn models_dir() -> PathBuf {
    home().join(".whispy/models")
}

/// Directory holding the int8 Parakeet TDT 0.6b v3 ONNX files:
/// `WHISPY_PARAKEET_DIR`, else the snapshot V1 already downloaded, else the
/// copy the app downloaded under [`models_dir`].
pub fn parakeet_dir() -> Result<PathBuf, Error> {
    if let Some(dir) = env::var_os("WHISPY_PARAKEET_DIR") {
        return checked_parakeet_dir(PathBuf::from(dir));
    }
    let repository = hub_cache().join(PARAKEET_REPOSITORY);
    let from_v1 = fs::read_to_string(repository.join("refs/main"))
        .ok()
        .map(|revision| repository.join("snapshots").join(revision.trim()))
        .and_then(|dir| checked_parakeet_dir(dir).ok());
    if let Some(dir) = from_v1 {
        return Ok(dir);
    }
    let downloaded = models_dir().join(PARAKEET_DOWNLOAD_DIR);
    checked_parakeet_dir(downloaded.clone()).map_err(|_| {
        Error::ModelMissing(format!(
            "no Parakeet model under {} or {} (Whispy downloads it at launch; or set WHISPY_PARAKEET_DIR to a directory holding {})",
            repository.display(),
            downloaded.display(),
            PARAKEET_FILES.join(", ")
        ))
    })
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

/// whisper.cpp small model: `WHISPY_WHISPER_MODEL`, else `~/.whispy/models/`
/// (where the app downloads it), else `~/.jarvis/models/`.
pub fn whisper_model() -> Result<PathBuf, Error> {
    if let Some(path) = env::var_os("WHISPY_WHISPER_MODEL") {
        return existing(PathBuf::from(path));
    }
    let candidates = [
        models_dir().join(WHISPER_FILE),
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

/// One model file to fetch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Download {
    pub url: String,
    pub path: PathBuf,
    pub sha256: &'static str,
    pub bytes: u64,
}

/// The files the app must download before it can load: none when every model
/// is found (an override set by hand counts as found, even if broken: the load
/// then says what is wrong with it).
pub fn missing_downloads() -> Vec<Download> {
    let parakeet_found = env::var_os("WHISPY_PARAKEET_DIR").is_some() || parakeet_dir().is_ok();
    let whisper_found = env::var_os("WHISPY_WHISPER_MODEL").is_some() || whisper_model().is_ok();
    plan(parakeet_found, whisper_found, &models_dir())
}

fn plan(parakeet_found: bool, whisper_found: bool, models_dir: &Path) -> Vec<Download> {
    let mut downloads = Vec::new();
    if !parakeet_found {
        let dir = models_dir.join(PARAKEET_DOWNLOAD_DIR);
        for (index, file) in PARAKEET_FILES.iter().enumerate() {
            let path = dir.join(file);
            if !path.is_file() {
                downloads.push(Download {
                    url: format!("{PARAKEET_URL}/{file}"),
                    path,
                    sha256: PARAKEET_SHA256[index],
                    bytes: PARAKEET_BYTES[index],
                });
            }
        }
    }
    if !whisper_found {
        downloads.push(Download {
            url: format!("{WHISPER_URL}/{WHISPER_FILE}"),
            path: models_dir.join(WHISPER_FILE),
            sha256: WHISPER_SHA256,
            bytes: WHISPER_BYTES,
        });
    }
    downloads
}

/// Fetches every file of [`missing_downloads`], one after the other. Each one
/// goes to `<file>.part` (a later launch resumes it), is checked against its
/// SHA-256, then renamed into place. Uses the system `curl`, so no network
/// code ships in Whispy.
pub fn download_missing() -> Result<(), Error> {
    for download in missing_downloads() {
        fetch(&download)?;
    }
    Ok(())
}

/// Downloads one file to its place, checked. A file whose checksum does not
/// match is deleted, so the next try starts afresh.
pub fn fetch(download: &Download) -> Result<(), Error> {
    let failed =
        |why: String| Error::ModelMissing(format!("could not download {}: {why}", download.url));
    if let Some(parent) = download.path.parent() {
        fs::create_dir_all(parent).map_err(|error| failed(error.to_string()))?;
    }
    let mut part = download.path.clone().into_os_string();
    part.push(".part");
    let part = PathBuf::from(part);
    let status = Command::new("curl")
        .args(["--fail", "--location", "--silent", "--show-error"])
        .args(["--retry", "3", "--retry-delay", "2", "--continue-at", "-"])
        .arg("--output")
        .arg(&part)
        .arg(&download.url)
        .status()
        .map_err(|error| failed(format!("curl did not start ({error})")))?;
    if !status.success() {
        return Err(failed(format!("curl exited with {status}")));
    }
    let actual = sha256(&part).map_err(failed)?;
    if actual != download.sha256 {
        let _ = fs::remove_file(&part);
        return Err(failed(format!(
            "checksum mismatch (expected {}, got {actual})",
            download.sha256
        )));
    }
    fs::rename(&part, &download.path).map_err(|error| failed(error.to_string()))
}

/// SHA-256 of a file, through `shasum` (macOS) or `sha256sum` (Linux).
fn sha256(path: &Path) -> Result<String, String> {
    let attempts: [(&str, &[&str]); 2] = [("shasum", &["-a", "256"]), ("sha256sum", &[])];
    for (program, args) in attempts {
        if let Ok(output) = Command::new(program).args(args).arg(path).output() {
            if output.status.success() {
                let text = String::from_utf8_lossy(&output.stdout);
                if let Some(digest) = text.split_whitespace().next() {
                    return Ok(digest.to_lowercase());
                }
            }
        }
    }
    Err(format!("no checksum tool could read {}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = env::temp_dir().join(format!("whispy-models-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn nothing_is_planned_when_both_models_are_found() {
        assert!(plan(true, true, Path::new("/nowhere")).is_empty());
    }

    #[test]
    fn a_fresh_install_plans_the_three_parakeet_files_and_whisper_small() {
        let dir = scratch("fresh");
        let planned = plan(false, false, &dir);
        let names: Vec<_> = planned
            .iter()
            .map(|d| d.path.file_name().unwrap().to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            names,
            [
                "encoder-model.int8.onnx",
                "decoder_joint-model.int8.onnx",
                "vocab.txt",
                "ggml-small.bin"
            ]
        );
        assert!(planned
            .iter()
            .all(|d| d.url.starts_with("https://huggingface.co/")));
        assert!(planned.iter().all(|d| d.sha256.len() == 64));
        assert_eq!(planned[3].path, dir.join("ggml-small.bin"));
    }

    #[test]
    fn a_parakeet_file_already_downloaded_is_not_fetched_again() {
        let dir = scratch("partial");
        let parakeet = dir.join(PARAKEET_DOWNLOAD_DIR);
        fs::create_dir_all(&parakeet).unwrap();
        fs::write(parakeet.join("vocab.txt"), "x").unwrap();
        let planned = plan(false, true, &dir);
        assert_eq!(planned.len(), 2);
        assert!(planned.iter().all(|d| !d.path.ends_with("vocab.txt")));
    }

    #[test]
    fn a_checked_file_lands_in_place_and_a_wrong_one_is_dropped() {
        let dir = scratch("fetch");
        let source = dir.join("source.bin");
        fs::write(&source, "hello\n").unwrap();
        let url = format!("file://{}", source.display());
        let good = Download {
            url: url.clone(),
            path: dir.join("out/good.bin"),
            // sha256 of "hello\n"
            sha256: "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
            bytes: 6,
        };
        fetch(&good).unwrap();
        assert_eq!(fs::read_to_string(&good.path).unwrap(), "hello\n");

        let bad = Download {
            sha256: "0000000000000000000000000000000000000000000000000000000000000000",
            path: dir.join("out/bad.bin"),
            ..good
        };
        let error = fetch(&bad).unwrap_err().to_string();
        assert!(error.contains("checksum mismatch"), "{error}");
        assert!(!bad.path.exists());
        assert!(!dir.join("out/bad.bin.part").exists());
    }
}

/// The real thing, once, by hand: a fresh home gets both models from the
/// network, checked, and the default pipeline loads from them.
/// `cargo test --release -p whispy-core -- --ignored --exact models::network::a_fresh_home_downloads_both_models_and_the_pipeline_loads`
#[cfg(test)]
mod network {
    use super::*;

    #[test]
    #[ignore = "downloads about 1.2 GB"]
    fn a_fresh_home_downloads_both_models_and_the_pipeline_loads() {
        let home = env::temp_dir().join(format!("whispy-fresh-home-{}", std::process::id()));
        let _ = fs::remove_dir_all(&home);
        fs::create_dir_all(&home).unwrap();
        // Run alone, by name: it owns the environment.
        env::set_var("HOME", &home);
        env::set_var("HF_HUB_CACHE", home.join("hf"));
        env::remove_var("HF_HOME");
        env::remove_var("WHISPY_PARAKEET_DIR");
        env::remove_var("WHISPY_WHISPER_MODEL");
        assert_eq!(missing_downloads().len(), 4);
        download_missing().unwrap();
        assert!(missing_downloads().is_empty());
        assert_eq!(
            parakeet_dir().unwrap(),
            home.join(".whispy/models").join(PARAKEET_DOWNLOAD_DIR)
        );
        assert_eq!(
            whisper_model().unwrap(),
            home.join(".whispy/models/ggml-small.bin")
        );
        crate::Pipeline::load_default().unwrap();
        let _ = fs::remove_dir_all(&home);
    }
}

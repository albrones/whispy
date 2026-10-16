//! Whispy V1 on the same clips, through its own Python engine (read-only).

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::corpus::bench_dir;

/// V1's text and transcription time for each clip path it was given.
pub type V1Results = HashMap<PathBuf, Vec<(String, f64)>>;

fn repository_root() -> PathBuf {
    bench_dir().join("../..")
}

/// `WHISPY_V1_PYTHON`, else the repository's `.venv` (V1's install).
pub fn python() -> PathBuf {
    std::env::var_os("WHISPY_V1_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| repository_root().join(".venv/bin/python"))
}

/// Runs `bench/v1_replay.py` over `paths` (a path may repeat, for latency).
/// Offline (`HF_HUB_OFFLINE=1`) and with a private TMPDIR, so V1's temp
/// cleanup never touches the installed daemon's files.
pub fn transcribe(paths: &[PathBuf], work_dir: &Path) -> Result<V1Results, String> {
    let python = python();
    if !python.is_file() {
        return Err(format!(
            "no V1 interpreter at {} (set WHISPY_V1_PYTHON to V1's venv python)",
            python.display()
        ));
    }
    let temp_dir = work_dir.join("v1-tmp");
    std::fs::create_dir_all(&temp_dir)
        .map_err(|error| format!("{}: {error}", temp_dir.display()))?;
    let script = bench_dir().join("v1_replay.py");
    let mut child = Command::new(&python)
        .args(["-I", "-B"])
        .arg(&script)
        .env("TMPDIR", &temp_dir)
        .env("HF_HUB_OFFLINE", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("cannot start {}: {error}", python.display()))?;
    {
        let mut stdin = child.stdin.take().ok_or("V1 replay has no stdin")?;
        let list: String = paths
            .iter()
            .map(|path| format!("{}\n", path.display()))
            .collect();
        stdin
            .write_all(list.as_bytes())
            .map_err(|error| format!("writing to V1 replay: {error}"))?;
    }
    let stdout = child.stdout.take().ok_or("V1 replay has no stdout")?;
    let requested: std::collections::HashSet<&PathBuf> = paths.iter().collect();
    let mut results: V1Results = HashMap::new();
    for line in BufReader::new(stdout).lines() {
        let line = line.map_err(|error| format!("reading V1 replay: {error}"))?;
        let mut fields = line.splitn(3, '\t');
        let (Some(path), Some(seconds), text) = (fields.next(), fields.next(), fields.next())
        else {
            continue; // V1 also prints its own progress lines.
        };
        if !requested.contains(&PathBuf::from(path)) {
            continue;
        }
        let seconds: f64 = seconds
            .parse()
            .map_err(|_| format!("unexpected V1 time {seconds:?} in {line:?}"))?;
        results
            .entry(PathBuf::from(path))
            .or_default()
            .push((text.unwrap_or("").to_string(), seconds));
    }
    let status = child
        .wait()
        .map_err(|error| format!("waiting for V1 replay: {error}"))?;
    if !status.success() || results.len() < requested.len() {
        return Err(format!(
            "V1 replay exited with {status} after {} of {} clips",
            results.len(),
            paths.len()
        ));
    }
    Ok(results)
}

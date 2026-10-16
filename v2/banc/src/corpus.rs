//! The clips the bench replays, and where they come from.

use std::path::{Path, PathBuf};

use whispy_core::audio::{self, SAMPLE_RATE};

/// The level the real lost dictations were measured at (V1 lost-speech-probe:
/// whole-clip RMS 0.010-0.013); the quiet group replays the references there.
const QUIET_RMS: f32 = 0.012;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Group {
    /// Real clips V1 lost (~/.whispy/lost/), no known text.
    Lost,
    /// Synthetic voices with a known text, at the level `say` speaks.
    Reference,
    /// The short and sentence references, turned down to the level of real lost dictation.
    Quiet,
    /// Silence and noise: any text here is invented.
    NonSpeech,
}

impl Group {
    pub fn name(self) -> &'static str {
        match self {
            Group::Lost => "lost",
            Group::Reference => "reference",
            Group::Quiet => "quiet",
            Group::NonSpeech => "non-speech",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Short,
    /// About 5 s: the latency target of criterion 4.
    Sentence,
    Long,
    Unknown,
}

pub struct Clip {
    pub id: String,
    pub group: Group,
    pub kind: Kind,
    pub expected: Option<String>,
    pub samples: Vec<f32>,
    /// A WAV copy in the bench's work directory, the file V1 reads.
    pub path: PathBuf,
}

pub fn bench_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../bench")
}

pub fn lost_dir() -> PathBuf {
    std::env::var_os("WHISPY_LOST_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".whispy/lost")
        })
}

/// Every clip of every group, each also written to `work_dir` as a WAV.
pub fn load(work_dir: &Path) -> Result<Vec<Clip>, String> {
    let mut clips = Vec::new();
    for (id, samples) in lost_clips()? {
        clips.push(clip(
            work_dir,
            id,
            Group::Lost,
            Kind::Unknown,
            None,
            samples,
        )?);
    }
    let references = reference_clips()?;
    for (id, kind, text, samples) in &references {
        clips.push(clip(
            work_dir,
            id.clone(),
            Group::Reference,
            *kind,
            Some(text.clone()),
            samples.clone(),
        )?);
    }
    for (id, kind, text, samples) in references
        .iter()
        .filter(|(_, kind, _, _)| *kind != Kind::Long)
    {
        let quiet = scaled_to_rms(samples, QUIET_RMS);
        clips.push(clip(
            work_dir,
            format!("{id}-quiet"),
            Group::Quiet,
            *kind,
            Some(text.clone()),
            quiet,
        )?);
    }
    for (id, samples) in non_speech_clips() {
        clips.push(clip(
            work_dir,
            id,
            Group::NonSpeech,
            Kind::Unknown,
            Some(String::new()),
            samples,
        )?);
    }
    Ok(clips)
}

fn clip(
    work_dir: &Path,
    id: String,
    group: Group,
    kind: Kind,
    expected: Option<String>,
    samples: Vec<f32>,
) -> Result<Clip, String> {
    let path = work_dir.join(format!("{}-{id}.wav", group.name()));
    audio::write_wav(&path, &samples).map_err(|error| error.to_string())?;
    Ok(Clip {
        id,
        group,
        kind,
        expected,
        samples,
        path,
    })
}

/// The lost clips, read into memory once: V1 keeps rotating that folder.
fn lost_clips() -> Result<Vec<(String, Vec<f32>)>, String> {
    let dir = lost_dir();
    let entries = std::fs::read_dir(&dir)
        .map_err(|error| format!("cannot read lost clips in {}: {error}", dir.display()))?;
    let mut paths: Vec<PathBuf> = entries
        .filter_map(|entry| entry.ok().map(|entry| entry.path()))
        .filter(|path| path.extension().is_some_and(|extension| extension == "wav"))
        .collect();
    paths.sort();
    paths
        .into_iter()
        .map(|path| {
            let id = path
                .file_stem()
                .map(|stem| {
                    stem.to_string_lossy()
                        .trim_start_matches("lost-")
                        .to_string()
                })
                .unwrap_or_default();
            audio::read_wav(&path)
                .map(|samples| (id, samples))
                .map_err(|error| error.to_string())
        })
        .collect()
}

/// One reference clip: id, kind, expected text, samples.
type Reference = (String, Kind, String, Vec<f32>);

/// `bench/reference/manifest.tsv`: `<file> <lang> <kind> <text>` per line.
fn reference_clips() -> Result<Vec<Reference>, String> {
    let dir = bench_dir().join("reference");
    let manifest_path = dir.join("manifest.tsv");
    let manifest = std::fs::read_to_string(&manifest_path)
        .map_err(|error| format!("{}: {error}", manifest_path.display()))?;
    manifest
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| {
            let fields: Vec<&str> = line.split('\t').collect();
            let [file, _lang, kind, text] = fields[..] else {
                return Err(format!(
                    "{}: malformed line {line:?}, expected 4 tab-separated fields",
                    manifest_path.display()
                ));
            };
            let kind = match kind {
                "short" => Kind::Short,
                "sentence" => Kind::Sentence,
                "long" => Kind::Long,
                other => {
                    return Err(format!(
                        "{}: unknown kind {other:?}, expected short, sentence or long",
                        manifest_path.display()
                    ))
                }
            };
            let path = dir.join(file);
            let samples = audio::read_wav(&path).map_err(|error| error.to_string())?;
            let id = Path::new(file)
                .file_stem()
                .map(|stem| stem.to_string_lossy().into_owned())
                .unwrap_or_default();
            Ok((id, kind, text.to_string(), samples))
        })
        .collect()
}

pub fn scaled_to_rms(samples: &[f32], target: f32) -> Vec<f32> {
    let level = audio::rms(samples);
    if level == 0.0 {
        return samples.to_vec();
    }
    samples
        .iter()
        .map(|&s| (s * target / level).clamp(-1.0, 1.0))
        .collect()
}

/// Deterministic noise (a fixed-seed LCG), so every run hears the same thing.
fn noise(seconds: f32, seed: u64) -> Vec<f32> {
    let mut state = seed;
    (0..(seconds * SAMPLE_RATE as f32) as usize)
        .map(|_| {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((state >> 33) as f32 / (1u64 << 31) as f32) * 2.0 - 1.0
        })
        .collect()
}

fn non_speech_clips() -> Vec<(String, Vec<f32>)> {
    let white = noise(3.0, 7);
    let mut brown = Vec::with_capacity(white.len());
    let mut level = 0.0f32;
    for &step in &white {
        level = (level + step * 0.02) * 0.995;
        brown.push(level);
    }
    let hum: Vec<f32> = (0..3 * SAMPLE_RATE as usize)
        .map(|i| (2.0 * std::f32::consts::PI * 50.0 * i as f32 / SAMPLE_RATE as f32).sin())
        .collect();
    vec![
        (
            "silence-3s".to_string(),
            vec![0.0; 3 * SAMPLE_RATE as usize],
        ),
        (
            "white-noise-rms-0.008".to_string(),
            scaled_to_rms(&white, 0.008),
        ),
        (
            "white-noise-rms-0.03".to_string(),
            scaled_to_rms(&white, 0.03),
        ),
        (
            "brown-noise-rms-0.02".to_string(),
            scaled_to_rms(&brown, 0.02),
        ),
        ("hum-50hz-rms-0.02".to_string(), scaled_to_rms(&hum, 0.02)),
    ]
}

/// About `seconds` of dictation: the reference sentences and long clips back
/// to back with 0.7 s pauses, looped.
pub fn long_dictation(seconds: f32) -> Result<Vec<f32>, String> {
    let speech: Vec<Vec<f32>> = reference_clips()?
        .into_iter()
        .filter(|(_, kind, _, _)| *kind != Kind::Short)
        .map(|(_, _, _, samples)| samples)
        .collect();
    if speech.is_empty() {
        return Err(
            "no sentence or long reference clip to build a long dictation from".to_string(),
        );
    }
    let target = (seconds * SAMPLE_RATE as f32) as usize;
    let pause = vec![0.0; (0.7 * SAMPLE_RATE as f32) as usize];
    let mut dictation = Vec::with_capacity(target);
    for samples in speech.iter().cycle() {
        if dictation.len() >= target {
            break;
        }
        dictation.extend_from_slice(samples);
        dictation.extend_from_slice(&pause);
    }
    dictation.truncate(target);
    Ok(dictation)
}

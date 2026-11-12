//! Criterion 3 on the user's own labels: `banc --labelled [dir]`.
//!
//! The directory (default `~/.whispy/bench`, the corpus of V1's
//! `scripts/quality_bench.py`) holds `<id>.wav` next to `<id>.json`:
//! `{"ref": "...", "kind": "chunk" | "noise" | "dictation", "reviewed": bool}`,
//! and `baseline.json`, V1's per-clip result on the same clips. The clips, the
//! references and V1's texts are the user's words and stay local: this module
//! reads them and prints numbers; it writes nothing.
//!
//! The verdict has three parts: (a) lost "chunk" clips come back with text for
//! at least 70 %; (b) no text is invented on lost "noise" clips; (c) the word
//! error rate over chunk and dictation clips is not worse than V1's, with V1's
//! own text normalization (`normalize` in `quality_bench.py`) so the two compare.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

use whispy_core::json::{parse_json, Json};
use whispy_core::Pipeline;

use crate::wer::word_edits;

/// Share of lost chunk clips that must come back with text.
const RECOVERY_TARGET_PERCENT: usize = 70;

// --- scoring ----------------------------------------------------------------

/// Words as V1's `quality_bench.normalize` reads them: lowercase, and every
/// character outside `a-z 0-9 à-ÿ` becomes a space (apostrophes and hyphens
/// split). Not `wer::normalized_words`, whose alphabet is wider.
pub fn v1_words(text: &str) -> Vec<String> {
    let spaced: String = text
        .to_lowercase()
        .chars()
        .map(|c| match c {
            'a'..='z' | '0'..='9' | '\u{e0}'..='\u{ff}' => c,
            _ => ' ',
        })
        .collect();
    spaced.split_whitespace().map(str::to_string).collect()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Chunk,
    Noise,
    Dictation,
}

impl Kind {
    fn parse(text: &str) -> Option<Kind> {
        match text {
            "chunk" => Some(Kind::Chunk),
            "noise" => Some(Kind::Noise),
            "dictation" => Some(Kind::Dictation),
            _ => None,
        }
    }
}

/// Where the clip came from, read off its id (`lost-…`, `drift-…`, `dictation-…`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Origin {
    Lost,
    Drift,
    Dictation,
    Other,
}

impl Origin {
    fn of(id: &str) -> Origin {
        match id.split('-').next() {
            Some("lost") => Origin::Lost,
            Some("drift") => Origin::Drift,
            Some("dictation") => Origin::Dictation,
            _ => Origin::Other,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Label {
    pub kind: Kind,
    pub reference: String,
    pub reviewed: bool,
}

/// A clip's sidecar. Like V1's bench, a clip counts only when `reviewed` is true.
pub fn parse_label(json: &str) -> Result<Label, String> {
    let value = parse_json(json)?;
    let kind = value
        .get("kind")
        .and_then(Json::text)
        .and_then(Kind::parse)
        .ok_or("\"kind\" must be chunk, noise or dictation")?;
    let reference = match value.get("ref") {
        None => String::new(),
        Some(Json::Text(text)) => text.clone(),
        Some(_) => return Err("\"ref\" must be a string".to_string()),
    };
    Ok(Label {
        kind,
        reference,
        reviewed: value.get("reviewed") == Some(&Json::Bool(true)),
    })
}

/// What V1 got on a clip, from `baseline.json`.
#[derive(Clone, Debug, PartialEq)]
pub struct V1Result {
    pub errors: usize,
    pub ref_len: usize,
    pub produced_text: bool,
}

pub fn parse_baseline(json: &str) -> Result<HashMap<String, V1Result>, String> {
    let value = parse_json(json)?;
    let Some(Json::Object(clips)) = value.get("clips") else {
        return Err("baseline.json has no \"clips\" object".to_string());
    };
    let mut results = HashMap::new();
    for (id, clip) in clips {
        let count = |key: &str| {
            clip.get(key)
                .and_then(Json::number)
                .map(|n| n as usize)
                .ok_or(format!("baseline clip {id}: no number {key:?}"))
        };
        results.insert(
            id.clone(),
            V1Result {
                errors: count("errors")?,
                ref_len: count("ref_len")?,
                produced_text: clip
                    .get("text")
                    .and_then(Json::text)
                    .is_some_and(|text| !text.trim().is_empty()),
            },
        );
    }
    Ok(results)
}

/// One clip scored: V2's text against the label.
#[derive(Clone, Debug, PartialEq)]
pub struct Scored {
    pub id: String,
    pub kind: Kind,
    pub origin: Origin,
    pub ref_len: usize,
    pub errors: usize,
    pub text_words: usize,
    pub has_text: bool,
}

pub fn score(id: &str, label: &Label, text: &str) -> Scored {
    // As in quality_bench: a noise clip has no reference, every word is an error.
    let expected = match label.kind {
        Kind::Noise => Vec::new(),
        _ => v1_words(&label.reference),
    };
    let actual = v1_words(text);
    Scored {
        id: id.to_string(),
        kind: label.kind,
        origin: Origin::of(id),
        ref_len: expected.len(),
        errors: word_edits(&expected, &actual),
        text_words: actual.len(),
        has_text: !text.trim().is_empty(),
    }
}

fn percent(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        100.0 * numerator as f64 / denominator as f64
    }
}

/// The three parts of criterion 3, over scored clips and V1's baseline.
#[derive(Clone, Debug, PartialEq)]
pub struct Verdict {
    /// Lost chunk clips, and how many came back with text (V2, V1).
    pub lost_chunks: usize,
    pub lost_recovered: usize,
    pub lost_recovered_v1: usize,
    /// Lost noise clips, and how many got invented text (V2, V1).
    pub lost_noise: usize,
    pub lost_noise_invented: usize,
    pub lost_noise_invented_v1: usize,
    /// The same on the drift noise clips (reported, not part of the verdict).
    pub drift_noise: usize,
    pub drift_noise_invented: usize,
    pub drift_noise_invented_v1: usize,
    /// Word errors over the chunk and dictation clips V1 also scored.
    pub wer_clips: usize,
    pub wer_words: usize,
    pub v2_errors: usize,
    pub v1_errors: usize,
}

impl Verdict {
    pub fn build(scored: &[Scored], baseline: &HashMap<String, V1Result>) -> Verdict {
        let v1_text = |id: &str| baseline.get(id).is_some_and(|r| r.produced_text);
        let count = |origin: Origin, kind: Kind, keep: &dyn Fn(&Scored) -> bool| {
            scored
                .iter()
                .filter(|s| s.origin == origin && s.kind == kind && keep(s))
                .count()
        };
        let any = |_: &Scored| true;
        let mut verdict = Verdict {
            lost_chunks: count(Origin::Lost, Kind::Chunk, &any),
            lost_recovered: count(Origin::Lost, Kind::Chunk, &|s| s.has_text),
            lost_recovered_v1: count(Origin::Lost, Kind::Chunk, &|s| v1_text(&s.id)),
            lost_noise: count(Origin::Lost, Kind::Noise, &any),
            lost_noise_invented: count(Origin::Lost, Kind::Noise, &|s| s.has_text),
            lost_noise_invented_v1: count(Origin::Lost, Kind::Noise, &|s| v1_text(&s.id)),
            drift_noise: count(Origin::Drift, Kind::Noise, &any),
            drift_noise_invented: count(Origin::Drift, Kind::Noise, &|s| s.has_text),
            drift_noise_invented_v1: count(Origin::Drift, Kind::Noise, &|s| v1_text(&s.id)),
            wer_clips: 0,
            wer_words: 0,
            v2_errors: 0,
            v1_errors: 0,
        };
        for clip in scored.iter().filter(|s| s.kind != Kind::Noise) {
            let Some(v1) = baseline.get(&clip.id) else {
                continue;
            };
            verdict.wer_clips += 1;
            verdict.wer_words += clip.ref_len;
            verdict.v2_errors += clip.errors;
            verdict.v1_errors += v1.errors;
        }
        verdict
    }

    /// At least 70 % of the lost chunk clips, in integer arithmetic.
    pub fn recovery_holds(&self) -> bool {
        self.lost_chunks > 0
            && self.lost_recovered * 100 >= RECOVERY_TARGET_PERCENT * self.lost_chunks
    }

    pub fn no_invented_text(&self) -> bool {
        self.lost_noise_invented == 0
    }

    /// V2's word errors do not exceed V1's on the same clips.
    pub fn wer_holds(&self) -> bool {
        self.wer_words > 0 && self.v2_errors <= self.v1_errors
    }

    pub fn holds(&self) -> bool {
        self.recovery_holds() && self.no_invented_text() && self.wer_holds()
    }

    /// Clips the user labelled noise that came back with text, wherever
    /// they came from: each one would be typed into the user's window.
    pub fn noise_with_text(&self) -> usize {
        self.lost_noise_invented + self.drift_noise_invented
    }

    pub fn lines(&self) -> Vec<String> {
        let state = |ok: bool| if ok { "holds" } else { "NOT MET" };
        vec![
            format!(
                "(a) lost chunk clips with text: V2 {}/{} ({:.0} %), V1 {}/{}; target {} % -> {}",
                self.lost_recovered,
                self.lost_chunks,
                percent(self.lost_recovered, self.lost_chunks),
                self.lost_recovered_v1,
                self.lost_chunks,
                RECOVERY_TARGET_PERCENT,
                state(self.recovery_holds())
            ),
            format!(
                "(b) text invented on lost noise clips: V2 {}/{}, V1 {}/{} -> {}; \
                 on drift noise clips: V2 {}/{}, V1 {}/{}",
                self.lost_noise_invented,
                self.lost_noise,
                self.lost_noise_invented_v1,
                self.lost_noise,
                state(self.no_invented_text()),
                self.drift_noise_invented,
                self.drift_noise,
                self.drift_noise_invented_v1,
                self.drift_noise
            ),
            format!(
                "(c) WER over {} chunk and dictation clips ({} reference words): \
                 V2 {:.1} % ({} errors), V1 {:.1} % ({} errors) -> {}",
                self.wer_clips,
                self.wer_words,
                percent(self.v2_errors, self.wer_words),
                self.v2_errors,
                percent(self.v1_errors, self.wer_words),
                self.v1_errors,
                state(self.wer_holds())
            ),
        ]
    }
}

// --- the command ------------------------------------------------------------

pub fn default_dir() -> PathBuf {
    PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".whispy/bench")
}

/// V1's result per clip id, from `baseline.json`.
pub type Baseline = HashMap<String, V1Result>;

pub struct Clip {
    pub id: String,
    pub label: Label,
    pub wav: PathBuf,
}

/// The reviewed clips and V1's baseline the full bench ranks configurations
/// on: `WHISPY_LABELLED_DIR`, or `~/.whispy/bench`.
pub fn bench_set() -> Result<(Vec<Clip>, Baseline), String> {
    let dir = std::env::var_os("WHISPY_LABELLED_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(default_dir);
    let baseline = load_baseline(&dir)?;
    let (clips, _) = load_clips(&dir)?;
    if clips.is_empty() {
        return Err(format!("{}: no reviewed clip", dir.display()));
    }
    Ok((clips, baseline))
}

fn load_baseline(dir: &Path) -> Result<Baseline, String> {
    let path = dir.join("baseline.json");
    let json = std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    parse_baseline(&json).map_err(|e| format!("{}: {e}", path.display()))
}

fn load_clips(dir: &Path) -> Result<(Vec<Clip>, usize), String> {
    let entries = std::fs::read_dir(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    let mut wavs: Vec<PathBuf> = entries
        .filter_map(|entry| entry.ok().map(|entry| entry.path()))
        .filter(|path| {
            path.extension().is_some_and(|e| e == "wav")
                && !path.to_string_lossy().ends_with(".prev.wav")
        })
        .collect();
    wavs.sort();
    let mut clips = Vec::new();
    let mut unreviewed = 0;
    for wav in wavs {
        let id = wav
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        let sidecar = wav.with_extension("json");
        let json =
            std::fs::read_to_string(&sidecar).map_err(|e| format!("{}: {e}", sidecar.display()))?;
        let label = parse_label(&json).map_err(|e| format!("{}: {e}", sidecar.display()))?;
        if label.reviewed {
            clips.push(Clip { id, label, wav });
        } else {
            unreviewed += 1;
        }
    }
    Ok((clips, unreviewed))
}

pub fn run(args: &[String]) -> Result<ExitCode, String> {
    let dir = args.first().map(PathBuf::from).unwrap_or_else(default_dir);
    let (clips, unreviewed) = load_clips(&dir)?;
    let baseline = load_baseline(&dir)?;
    eprintln!(
        "banc: {} labelled clips from {} ({unreviewed} unreviewed skipped), default pipeline",
        clips.len(),
        dir.display()
    );
    let show_text = std::env::var_os("WHISPY_BANC_SHOW_LOST_TEXT").is_some_and(|v| v == "1");
    let mut pipeline = Pipeline::load_default().map_err(|e| e.to_string())?;
    let mut scored = Vec::new();
    let mut texts = Vec::new();
    for clip in &clips {
        let samples = whispy_core::audio::read_wav(&clip.wav).map_err(|e| e.to_string())?;
        let started = Instant::now();
        let transcript = pipeline.transcribe(&samples).map_err(|e| e.to_string())?;
        let seconds = started.elapsed().as_secs_f64();
        let result = score(&clip.id, &clip.label, &transcript.text);
        println!(
            "{:<34} {:<9} ref {:>3} words, V2 {:>3} words, {:<9} {:>5.1} s",
            result.id,
            format!("{:?}", result.kind).to_lowercase(),
            result.ref_len,
            result.text_words,
            transcript.engine.unwrap_or("-"),
            seconds
        );
        if show_text {
            texts.push((
                clip.id.clone(),
                clip.label.reference.clone(),
                transcript.text,
            ));
        }
        scored.push(result);
    }
    println!("\nWER per lost chunk clip (V2 against your reference; V1 from baseline.json):");
    for clip in scored
        .iter()
        .filter(|s| s.origin == Origin::Lost && s.kind == Kind::Chunk)
    {
        let v1 = baseline.get(&clip.id).map_or("n/a".to_string(), |r| {
            format!("{:.0} %", percent(r.errors, r.ref_len))
        });
        println!(
            "  {:<34} V2 {:>4.0} % ({} errors / {} words, {})  V1 {v1}",
            clip.id,
            percent(clip.errors, clip.ref_len),
            clip.errors,
            clip.ref_len,
            if clip.has_text { "text" } else { "empty" }
        );
    }
    if show_text {
        println!("\nLocal read (WHISPY_BANC_SHOW_LOST_TEXT=1), do not commit:");
        for (id, reference, text) in &texts {
            println!("  {id}\n    ref: {reference:?}\n    V2:  {text:?}");
        }
    }
    let missing: Vec<&str> = scored
        .iter()
        .filter(|s| !baseline.contains_key(&s.id))
        .map(|s| s.id.as_str())
        .collect();
    if !missing.is_empty() {
        println!(
            "\nNot in baseline.json (left out of the V1 comparison): {}",
            missing.join(", ")
        );
    }
    let verdict = Verdict::build(&scored, &baseline);
    println!("\nCriterion 3, on your labels:");
    for line in verdict.lines() {
        println!("  {line}");
    }
    // whisper's Metal backend asserts in a static destructor when the process
    // exits normally after it ran (SIGABRT, after all the output): leave
    // without running destructors. Nothing here needs flushing but stdout.
    {
        use std::io::Write;
        let _ = std::io::stdout().flush();
    }
    // SAFETY: `_exit` takes no pointers and never returns.
    unsafe { libc::_exit(if verdict.holds() { 0 } else { 1 }) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn label_needs_a_kind_and_reads_review() {
        let label =
            parse_label(r#"{"ref": "Bonjour.", "kind": "dictation", "reviewed": true}"#).unwrap();
        assert_eq!(label.kind, Kind::Dictation);
        assert_eq!(label.reference, "Bonjour.");
        assert!(label.reviewed);
        // A noise clip may leave the reference out; no "reviewed" means unreviewed.
        let label = parse_label(r#"{"kind": "noise"}"#).unwrap();
        assert_eq!(
            (label.kind, label.reference.as_str(), label.reviewed),
            (Kind::Noise, "", false)
        );
        assert!(parse_label(r#"{"ref": "x", "kind": "song"}"#).is_err());
        assert!(parse_label(r#"{"ref": 3, "kind": "chunk"}"#).is_err());
    }

    #[test]
    fn words_follow_the_python_normalization() {
        assert_eq!(
            v1_words("L'équipe, c’est ÇA!"),
            ["l", "équipe", "c", "est", "ça"]
        );
        // Hyphens split, and characters outside a-z0-9à-ÿ (œ) drop to a space.
        assert_eq!(v1_words("peut-être cœur"), ["peut", "être", "c", "ur"]);
    }

    fn label(kind: Kind, reference: &str) -> Label {
        Label {
            kind,
            reference: reference.to_string(),
            reviewed: true,
        }
    }

    #[test]
    fn empty_text_on_speech_costs_every_word_and_noise_text_is_all_errors() {
        let empty = score("lost-1", &label(Kind::Chunk, "un deux trois"), "");
        assert_eq!((empty.ref_len, empty.errors, empty.has_text), (3, 3, false));
        let exact = score(
            "lost-2",
            &label(Kind::Chunk, "un deux trois"),
            "Un deux, trois.",
        );
        assert_eq!((exact.errors, exact.has_text), (0, true));
        let invented = score("lost-3", &label(Kind::Noise, "ignored"), "thank you");
        assert_eq!(
            (invented.ref_len, invented.errors, invented.has_text),
            (0, 2, true)
        );
        assert_eq!(invented.origin, Origin::Lost);
    }

    fn v1(errors: usize, ref_len: usize, produced_text: bool) -> V1Result {
        V1Result {
            errors,
            ref_len,
            produced_text,
        }
    }

    #[test]
    fn baseline_reads_errors_and_whether_v1_typed_anything() {
        let baseline = parse_baseline(
            r#"{"totals": {}, "clips": {
                "lost-1": {"kind": "chunk", "ref_len": 3, "errors": 3, "text": ""},
                "drift-2": {"kind": "chunk", "ref_len": 5, "errors": 1, "text": "a b c d e"}}}"#,
        )
        .unwrap();
        assert_eq!(baseline["lost-1"], v1(3, 3, false));
        assert_eq!(baseline["drift-2"], v1(1, 5, true));
        assert!(parse_baseline("{}").is_err());
    }

    #[test]
    fn verdict_counts_recovery_noise_and_wer_on_the_common_clips() {
        let baseline: HashMap<String, V1Result> = [
            ("lost-a", v1(4, 4, false)),
            ("lost-b", v1(4, 4, false)),
            ("lost-n", v1(0, 0, false)),
            ("drift-n", v1(2, 0, true)),
            ("dictation-a", v1(2, 10, true)),
        ]
        .into_iter()
        .map(|(id, result)| (id.to_string(), result))
        .collect();
        let scored = vec![
            score(
                "lost-a",
                &label(Kind::Chunk, "un deux trois quatre"),
                "un deux trois",
            ),
            score("lost-b", &label(Kind::Chunk, "un deux trois quatre"), ""),
            score("lost-n", &label(Kind::Noise, ""), ""),
            score("drift-n", &label(Kind::Noise, ""), "oui"),
            score(
                "dictation-a",
                &label(Kind::Dictation, "a b c d e f g h i j"),
                "a b c d e f g h i j",
            ),
            // Not in the baseline: out of the WER comparison.
            score("dictation-z", &label(Kind::Dictation, "x y"), "z"),
        ];
        let verdict = Verdict::build(&scored, &baseline);
        assert_eq!(
            (
                verdict.lost_chunks,
                verdict.lost_recovered,
                verdict.lost_recovered_v1
            ),
            (2, 1, 0)
        );
        assert_eq!((verdict.lost_noise, verdict.lost_noise_invented), (1, 0));
        assert_eq!(
            (
                verdict.drift_noise,
                verdict.drift_noise_invented,
                verdict.drift_noise_invented_v1
            ),
            (1, 1, 1)
        );
        // lost-a, lost-b and dictation-a are in the baseline: 4 + 4 + 10 words.
        assert_eq!((verdict.wer_clips, verdict.wer_words), (3, 18));
        assert_eq!((verdict.v2_errors, verdict.v1_errors), (1 + 4, 4 + 4 + 2));
        assert!(!verdict.recovery_holds(), "1/2 is 50 %");
        assert!(verdict.no_invented_text());
        assert!(verdict.wer_holds());
        assert!(!verdict.holds());
        assert_eq!(verdict.lines().len(), 3);
    }

    #[test]
    fn recovery_target_is_seventy_percent_of_the_lost_chunks() {
        let mut verdict = Verdict::build(&[], &HashMap::new());
        assert!(!verdict.recovery_holds(), "no clips is not a pass");
        (verdict.lost_chunks, verdict.lost_recovered) = (7, 5);
        assert!(verdict.recovery_holds(), "5/7 is 71 %");
        verdict.lost_recovered = 4;
        assert!(!verdict.recovery_holds(), "4/7 is 57 %");
        (verdict.lost_chunks, verdict.lost_recovered) = (8, 6);
        assert!(verdict.recovery_holds(), "6/8 is 75 %");
        verdict.lost_recovered = 5;
        assert!(!verdict.recovery_holds(), "5/8 is 62 %");
    }
}

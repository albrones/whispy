//! Which lost clips really hold speech, per the reference model and the ear.
//!
//! `bench/oracle.py` (whisper large-v3-turbo) writes `bench/oracle/oracle.tsv`;
//! the user's verdicts from `bench/oracle/listen.html` go to
//! `bench/oracle/verdicts.tsv` and win over the oracle's class. Both files hold
//! the user's words and stay local (gitignored); the report prints counts only.

use std::collections::HashMap;
use std::path::Path;

use crate::corpus::bench_dir;
use crate::wer;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Class {
    /// The oracle decoded a confident French or English utterance, or the user heard one.
    Speech,
    /// Unsure: a stock one-liner or a low-confidence decode nobody has listened to yet.
    Doubtful,
    /// Breath, clicks or silence.
    NoSpeech,
}

impl Class {
    fn parse(text: &str) -> Option<Class> {
        match text {
            "speech" => Some(Class::Speech),
            "doubtful" => Some(Class::Doubtful),
            "no-speech" => Some(Class::NoSpeech),
            _ => None,
        }
    }
}

pub struct Label {
    pub class: Class,
    /// True when the user's verdict, not the oracle, set the class.
    pub is_heard: bool,
    /// What the oracle decoded: the stand-in reference for a recovered clip's WER.
    pub text: String,
}

/// Clip id (the lost file's name without `lost-` and `.wav`) → label.
pub type Labels = HashMap<String, Label>;

/// The labels, or why there are none (the oracle was never run).
pub fn load() -> Result<Labels, String> {
    let dir = bench_dir().join("oracle");
    let mut labels = read_oracle(&dir.join("oracle.tsv"))?;
    let verdicts = dir.join("verdicts.tsv");
    if verdicts.is_file() {
        apply_verdicts(&mut labels, &read(&verdicts)?)?;
    }
    Ok(labels)
}

fn read(path: &Path) -> Result<String, String> {
    std::fs::read_to_string(path).map_err(|error| {
        format!(
            "{}: {error} (run bench/oracle.py, see README.md)",
            path.display()
        )
    })
}

fn read_oracle(path: &Path) -> Result<Labels, String> {
    parse_oracle(&read(path)?, path)
}

fn parse_oracle(table: &str, path: &Path) -> Result<Labels, String> {
    let mut labels = Labels::new();
    for line in table.lines().filter(|line| !line.trim().is_empty()) {
        let fields: Vec<&str> = line.splitn(6, '\t').collect();
        let [clip, class, _language, _logprob, _words, text] = fields.as_slice() else {
            return Err(format!(
                "{}: expected 6 tab-separated fields, got {} in a line",
                path.display(),
                fields.len()
            ));
        };
        let class = Class::parse(class).ok_or_else(|| {
            format!(
                "{}: class {class:?}, expected speech, doubtful or no-speech",
                path.display()
            )
        })?;
        labels.insert(
            clip.to_string(),
            Label {
                class,
                is_heard: false,
                text: text.to_string(),
            },
        );
    }
    Ok(labels)
}

fn apply_verdicts(labels: &mut Labels, verdicts: &str) -> Result<(), String> {
    for line in verdicts.lines().filter(|line| !line.trim().is_empty()) {
        let (clip, verdict) = line.trim().split_once('\t').ok_or_else(|| {
            format!("verdicts.tsv: expected clip<TAB>speech|no-speech, got {line:?}")
        })?;
        let class = match Class::parse(verdict.trim()) {
            Some(class @ (Class::Speech | Class::NoSpeech)) => class,
            _ => {
                return Err(format!(
                    "verdicts.tsv: verdict {verdict:?} for {clip}, expected speech or no-speech"
                ))
            }
        };
        let label = labels.get_mut(clip).ok_or_else(|| {
            format!("verdicts.tsv: clip {clip} is not in oracle.tsv (rerun bench/oracle.py)")
        })?;
        label.class = class;
        label.is_heard = true;
    }
    Ok(())
}

/// How a configuration does on the lost clips that hold speech.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Recovery {
    pub recovered: usize,
    pub speech_clips: usize,
    /// Word errors against the oracle's text, over the recovered clips only.
    pub word_errors: usize,
    pub oracle_words: usize,
}

impl Recovery {
    pub fn rate(&self) -> f64 {
        if self.speech_clips == 0 {
            0.0
        } else {
            self.recovered as f64 / self.speech_clips as f64
        }
    }

    /// Words of the oracle the engine got wrong on the clips it recovered:
    /// "came back with text" is only half the story if the text is wrong.
    pub fn wer_against_oracle(&self) -> f64 {
        if self.oracle_words == 0 {
            0.0
        } else {
            self.word_errors as f64 / self.oracle_words as f64
        }
    }

    /// Adds one lost clip's outcome; ignored unless it holds speech.
    pub fn add(&mut self, label: Option<&Label>, text: &str) {
        let Some(label) = label.filter(|label| label.class == Class::Speech) else {
            return;
        };
        self.speech_clips += 1;
        if text.trim().is_empty() {
            return;
        }
        self.recovered += 1;
        let expected = wer::normalized_words(&label.text);
        self.word_errors += wer::word_edits(&expected, &wer::normalized_words(text));
        self.oracle_words += expected.len();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn labels() -> Labels {
        read_oracle_text("a\tspeech\tfr\t-0.3\t3\tà améliorer, je pense\nb\tdoubtful\ten\t-0.8\t2\tThank you.\nc\tno-speech\ten\t-1.4\t1\tso\n")
    }

    fn read_oracle_text(text: &str) -> Labels {
        parse_oracle(text, Path::new("oracle.tsv")).unwrap()
    }

    #[test]
    fn a_verdict_overrides_the_oracle() {
        let mut labels = labels();
        apply_verdicts(&mut labels, "b\tspeech\nc\tno-speech\n").unwrap();
        assert_eq!(labels["b"].class, Class::Speech);
        assert!(labels["b"].is_heard);
        assert!(apply_verdicts(&mut labels, "b\tmaybe\n").is_err());
        assert!(apply_verdicts(&mut labels, "zzz\tspeech\n").is_err());
    }

    #[test]
    fn only_speech_clips_count_and_wer_is_against_the_oracle() {
        let labels = labels();
        let mut recovery = Recovery::default();
        recovery.add(labels.get("a"), "À améliorer, je pense.");
        recovery.add(labels.get("b"), "Thank you.");
        recovery.add(labels.get("c"), "So.");
        recovery.add(None, "anything");
        assert_eq!((recovery.recovered, recovery.speech_clips), (1, 1));
        assert_eq!(recovery.wer_against_oracle(), 0.0);
        let mut missed = Recovery::default();
        missed.add(labels.get("a"), "");
        assert_eq!((missed.recovered, missed.speech_clips), (0, 1));
    }
}

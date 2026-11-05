//! The trial's numbers: one JSON line per finished dictation, without its text.
//!
//! `~/.whispy/v2/dictations.jsonl`, mode 0600, appended by the worker once the
//! outcome is known (after delivery for a dictation with text). `banc --trial`
//! reads it. The keys are fixed and the only strings are enum names and the
//! engine name, so the line is written by hand: no serialisation crate, and no
//! way for the transcript to slip in through a struct field.
//!
//! `time` is Unix seconds (an integer): the reader filters by date and needs
//! no parser for it. The log carries the human-readable RFC 3339 form.

use std::fs::OpenOptions;
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

use crate::controller::Source;
use crate::log;

pub const FILE_NAME: &str = "dictations.jsonl";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    /// Pasted into the frontmost app.
    Inserted,
    /// Left on the clipboard only (watchdog stop).
    Clipboard,
    /// Nothing to transcribe: silence the gates rejected.
    Empty,
    /// Audio at a level the microphone should not give: it heard nothing.
    HeardNothing,
    /// Speech the engines returned no text for: the clip is kept.
    Lost,
    /// The engine or the delivery failed.
    Failed,
}

impl Outcome {
    pub fn as_str(self) -> &'static str {
        match self {
            Outcome::Inserted => "inserted",
            Outcome::Clipboard => "clipboard",
            Outcome::Empty => "empty",
            Outcome::HeardNothing => "heard_nothing",
            Outcome::Lost => "lost",
            Outcome::Failed => "failed",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Entry {
    /// Unix seconds, when the outcome was known.
    pub time: u64,
    /// Length of the recording.
    pub duration_s: f32,
    /// Release to delivery done.
    pub latency_s: f32,
    pub trigger: Source,
    pub outcome: Outcome,
    pub engine: Option<String>,
    /// Characters of text, never the text.
    pub length: usize,
}

impl Entry {
    pub fn to_json(&self) -> String {
        let engine = match &self.engine {
            Some(name) => json_string(name),
            None => "null".to_string(),
        };
        format!(
            "{{\"time\":{},\"duration_s\":{:.3},\"latency_s\":{:.3},\"trigger\":{},\"outcome\":{},\"engine\":{engine},\"length\":{}}}",
            self.time,
            self.duration_s,
            self.latency_s,
            json_string(self.trigger.as_str()),
            json_string(self.outcome.as_str()),
            self.length
        )
    }

    /// The same facts as one log line.
    pub fn summary(&self) -> String {
        format!(
            "dictation: outcome={} trigger={} duration={:.1}s latency={:.2}s engine={} length={}",
            self.outcome.as_str(),
            self.trigger.as_str(),
            self.duration_s,
            self.latency_s,
            self.engine.as_deref().unwrap_or("none"),
            self.length
        )
    }
}

/// Where the journal lives; `None` writes nothing (tests, or no home directory).
pub struct Journal {
    pub directory: Option<PathBuf>,
}

impl Journal {
    pub fn append(&self, entry: &Entry) -> std::io::Result<()> {
        let Some(directory) = &self.directory else {
            return Ok(());
        };
        log::ensure_private_dir(directory)?;
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .mode(0o600)
            .open(directory.join(FILE_NAME))?;
        // One write call: a line is not interleaved with another process's.
        file.write_all(format!("{}\n", entry.to_json()).as_bytes())
    }

    /// Journal and log line for one dictation. A failed write is logged and
    /// nothing else: the dictation was already delivered.
    pub fn record(&self, entry: &Entry) {
        log::line(&entry.summary());
        if let Err(error) = self.append(entry) {
            log::line(&format!("could not write the journal: {error}"));
        }
    }
}

/// A JSON string literal: quotes, backslashes and control characters escaped.
pub fn json_string(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for character in text.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            control if (control as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", control as u32))
            }
            other => out.push(other),
        }
    }
    out.push('"');
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::log::testing::temp_dir;

    fn entry() -> Entry {
        Entry {
            time: 1_700_000_000,
            duration_s: 4.0,
            latency_s: 0.8125,
            trigger: Source::Fn,
            outcome: Outcome::Inserted,
            engine: Some("parakeet".into()),
            length: 42,
        }
    }

    #[test]
    fn an_inserted_dictation_has_every_field() {
        assert_eq!(
            entry().to_json(),
            "{\"time\":1700000000,\"duration_s\":4.000,\"latency_s\":0.812,\"trigger\":\"fn\",\"outcome\":\"inserted\",\"engine\":\"parakeet\",\"length\":42}"
        );
        let empty = Entry {
            engine: None,
            outcome: Outcome::HeardNothing,
            trigger: Source::Socket,
            ..entry()
        };
        assert!(empty.to_json().contains("\"engine\":null"));
        assert!(empty.to_json().contains("\"outcome\":\"heard_nothing\""));
        assert!(empty.to_json().contains("\"trigger\":\"socket\""));
    }

    #[test]
    fn lines_are_appended_with_mode_0600() {
        use std::os::unix::fs::PermissionsExt;
        let directory = temp_dir("journal-append").join("v2");
        let journal = Journal {
            directory: Some(directory.clone()),
        };
        journal.append(&entry()).unwrap();
        journal.append(&entry()).unwrap();
        let path = directory.join(FILE_NAME);
        assert_eq!(std::fs::read_to_string(&path).unwrap().lines().count(), 2);
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn strings_are_escaped() {
        assert_eq!(json_string("a\"b\\c\nd\u{1}"), "\"a\\\"b\\\\c\\nd\\u0001\"");
    }

    #[test]
    fn the_summary_names_the_outcome_but_has_no_text_field() {
        let summary = entry().summary();
        assert!(summary.contains("outcome=inserted"));
        assert!(summary.contains("length=42"));
    }
}

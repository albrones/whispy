//! Rolling re-transcription: type what is said while it is said, with the
//! quality of one block (V2's « Type while speaking »).
//!
//! The pieces of [`crate::split::LiveSplitter`] decide at a pause, with the
//! least context, and cannot take it back. This is « LocalAgreement »
//! (Macháček et al., 2023; NVIDIA's buffered Parakeet inference): the open
//! window (the audio since the last commit) is re-transcribed with word times
//! every [`PASS_EVERY_S`], and only text two consecutive passes agree on, word
//! for word, is committed. Audio is released only at a committed boundary, in
//! the middle of the gap after the last committed word, so no word is cut.
//!
//! A sentence is committed once it is stable up to its final `.`, `?`, `!` or
//! `…` and either more words follow or [`COMMIT_PAUSE_S`] of silence do: a
//! thinking pause shorter than that leaves the period provisional until the
//! model has seen what comes next. Run-on speech is committed by
//! [`FORCE_COMMIT_S`] at its longest stable gap, and the next text continues
//! that sentence ([`crate::join::lowercase_first`]). Past [`MAX_WINDOW_S`] the
//! window goes whole through the default pipeline.
//!
//! Every pushed sample ends in exactly one committed text or in the text
//! [`Streamer::finish`] returns (silence nobody spoke over is dropped): the
//! committed texts and the finish text, in order, are the dictation.
//!
//! A [`Streamer`] holds a [`VoiceDetector`] (a raw C pointer): like
//! [`crate::split::LiveSplitter`] it is not `Send`; create it on the thread
//! that drives it. No dictated text is ever logged here: [`PassStats`] is counts.

use std::time::Instant;

use crate::audio::SAMPLE_RATE;
use crate::join::lowercase_first;
use crate::split::MAX_PIECE_S;
use crate::vad::{VoiceDetector, FRAME_SAMPLES};
use crate::{Error, Pipeline, Word};

/// New audio, in seconds, between two passes.
pub const PASS_EVERY_S: f32 = 0.6;
/// Silence after a sentence end that commits it when nothing follows.
pub const COMMIT_PAUSE_S: f32 = 2.0;
/// A window this long without a committable sentence is committed at its longest stable gap.
pub const FORCE_COMMIT_S: f32 = 15.0;
/// No engine call gets more than this: past it the window is committed whole.
pub const MAX_WINDOW_S: f32 = MAX_PIECE_S;
/// What is kept of a window that holds no voice and no hypothesis: the start
/// of the next word needs its lead-in.
pub const LEADING_SILENCE_KEPT_S: f32 = 0.5;
/// Past the last committed word with nothing after it, the cut falls this far on.
const TAIL_KEPT_S: f32 = 0.3;

/// What one pass did. Counts only, never text: it goes to the log.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct PassStats {
    /// The open window's length when the pass began.
    pub window_s: f32,
    /// Time spent in the engine.
    pub took_s: f32,
    /// Words of the new hypothesis.
    pub words: usize,
    /// Words it shares with the previous hypothesis, from the start.
    pub stable: usize,
    pub committed_words: usize,
    /// The commit was cut mid-sentence (run-on or overflow).
    pub forced: bool,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Update {
    /// Text to append to the field now, already joined (leading space
    /// included); empty most passes.
    pub typed: String,
    /// The hypothesis after the committed text, words joined by spaces.
    pub provisional: String,
    pub stats: PassStats,
}

pub struct Streamer {
    /// The open window: the audio since the last commit.
    window: Vec<f32>,
    /// Samples since the last complete VAD frame.
    frame_tail: Vec<f32>,
    detector: VoiceDetector,
    /// One voiced flag per VAD frame since the stream began.
    voiced: Vec<bool>,
    /// Where the window starts, in samples since the stream began.
    window_start: usize,
    pushed_since_pass: usize,
    voiced_since_pass: bool,
    /// The last hypothesis after the committed text, times relative to the window.
    previous: Vec<Word>,
    committed: String,
    /// The last commit was cut mid-sentence.
    last_commit_forced: bool,
}

impl Default for Streamer {
    fn default() -> Self {
        Streamer::new()
    }
}

impl Streamer {
    pub fn new() -> Self {
        Streamer {
            window: Vec::new(),
            frame_tail: Vec::new(),
            detector: VoiceDetector::new(),
            voiced: Vec::new(),
            window_start: 0,
            pushed_since_pass: 0,
            voiced_since_pass: false,
            previous: Vec::new(),
            committed: String::new(),
            last_commit_forced: false,
        }
    }

    /// Appends `samples` (16 kHz mono, as the microphone gives them).
    pub fn push(&mut self, samples: &[f32]) {
        self.window.extend_from_slice(samples);
        self.pushed_since_pass += samples.len();
        self.frame_tail.extend_from_slice(samples);
        let (frames, _) = self.frame_tail.as_chunks::<FRAME_SAMPLES>();
        for frame in frames {
            let is_voiced = self.detector.is_voiced(frame);
            self.voiced.push(is_voiced);
            self.voiced_since_pass |= is_voiced;
        }
        let used = frames.len() * FRAME_SAMPLES;
        self.frame_tail.drain(..used);
    }

    /// At least [`PASS_EVERY_S`] of audio since the last pass, and either some
    /// of it is voiced or the last hypothesis is not empty: silence after
    /// everything is committed costs nothing.
    pub fn is_pass_due(&self) -> bool {
        self.pushed_since_pass as f32 >= PASS_EVERY_S * SAMPLE_RATE as f32
            && (self.voiced_since_pass || !self.previous.is_empty())
    }

    /// Everything committed so far: what the field holds.
    pub fn committed(&self) -> &str {
        &self.committed
    }

    /// One re-transcription of the open window; commits what is stable.
    pub fn pass(&mut self, pipeline: &mut Pipeline) -> Result<Update, Error> {
        self.pushed_since_pass = 0;
        self.voiced_since_pass = false;

        // 0. Nothing pending: what came before the last long pause is closed.
        let closed = self.close_before_pause(pipeline)?;
        let window_s = seconds(self.window.len());
        let mut stats = PassStats {
            window_s,
            ..PassStats::default()
        };
        if !closed.is_empty() {
            stats.committed_words = closed.split_whitespace().count();
            return Ok(Update {
                typed: closed,
                provisional: String::new(),
                stats,
            });
        }

        // 1. Nothing said and nothing pending: keep only the lead-in.
        if self.previous.is_empty() && !self.window_has_voice() {
            let kept = (LEADING_SILENCE_KEPT_S * SAMPLE_RATE as f32) as usize;
            let dropped = self.window.len().saturating_sub(kept);
            self.window.drain(..dropped);
            self.window_start += dropped;
            return Ok(Update {
                stats,
                ..Update::default()
            });
        }

        // 2. Overflow: the full default pipeline, committed whole.
        if window_s > MAX_WINDOW_S {
            let started = Instant::now();
            let text = pipeline.transcribe(&self.window)?.text;
            stats.took_s = started.elapsed().as_secs_f32();
            stats.committed_words = text.split_whitespace().count();
            stats.forced = true;
            self.release(self.window.len());
            self.previous.clear();
            return Ok(Update {
                typed: self.commit_text(&text, true),
                provisional: String::new(),
                stats,
            });
        }

        // 3. The hypothesis; an engine without timings never agrees with itself.
        let started = Instant::now();
        let mut hypothesis = pipeline.transcribe_timed(&self.window)?.unwrap_or_default();
        stats.took_s = started.elapsed().as_secs_f32();
        stats.words = hypothesis.len();

        // 4. The words two passes agree on, punctuation and case included.
        let stable = hypothesis
            .iter()
            .zip(&self.previous)
            .take_while(|(new, old)| new.text == old.text)
            .count();
        stats.stable = stable;

        // 5. A sentence, stable up to its end, that speech or a long pause follows.
        let sentence_end = (0..stable).rev().find(|&i| {
            ends_a_sentence(&hypothesis[i].text)
                && (i + 1 < hypothesis.len() || window_s - hypothesis[i].end_s >= COMMIT_PAUSE_S)
        });
        // 5b. Else everything stable, when the speaker has stopped that long
        // with no sentence end: the model reads it as unfinished, so what
        // follows continues it. Without this, silence would cost a pass every
        // PASS_EVERY_S until the run-on cut.
        let paused_after_all = stable > 0
            && stable == hypothesis.len()
            && window_s - hypothesis[stable - 1].end_s >= COMMIT_PAUSE_S;
        // 6. Else a run-on window is cut at its longest stable gap.
        let commit = match sentence_end {
            Some(i) => Some((i, false)),
            None if paused_after_all => Some((stable - 1, true)),
            None if window_s >= FORCE_COMMIT_S => {
                longest_gap(&hypothesis, stable).map(|i| (i, true))
            }
            None => None,
        };

        // 7. Commit, release the audio, keep what follows as the hypothesis.
        let Some((i, forced)) = commit else {
            let provisional = joined(&hypothesis);
            self.previous = hypothesis;
            return Ok(Update {
                typed: String::new(),
                provisional,
                stats,
            });
        };
        let cut_s = match hypothesis.get(i + 1) {
            Some(next) => (hypothesis[i].end_s + next.start_s) / 2.0,
            None => hypothesis[i].end_s + TAIL_KEPT_S,
        }
        .clamp(0.0, window_s);
        self.release((cut_s * SAMPLE_RATE as f32) as usize);
        let mut rest = hypothesis.split_off(i + 1);
        for word in &mut rest {
            word.start_s = (word.start_s - cut_s).max(0.0);
            word.end_s = (word.end_s - cut_s).max(0.0);
        }
        let typed = self.commit_text(&joined(&hypothesis), forced);
        stats.committed_words = i + 1;
        stats.forced = forced;
        let provisional = joined(&rest);
        self.previous = rest;
        Ok(Update {
            typed,
            provisional,
            stats,
        })
    }

    /// The text to append at the stop: the open window goes through the full
    /// default pipeline (gates, padding, fallback, 20 s split). When it holds
    /// nothing and the last commit was cut mid-sentence, a `.` closes it.
    pub fn finish(self, pipeline: &mut Pipeline) -> Result<String, Error> {
        let text = pipeline.transcribe(&self.window)?.text;
        Ok(self.finish_with(&text))
    }

    /// The open window at the stop, for a caller that transcribes it itself
    /// (the app, which keeps a lost clip and the engine's name) before
    /// [`finish_with`](Streamer::finish_with).
    pub fn rest(&self) -> &[f32] {
        &self.window
    }

    /// [`finish`](Streamer::finish) with the rest already transcribed as `text`.
    pub fn finish_with(mut self, text: &str) -> String {
        let typed = self.commit_text(text, false);
        if typed.is_empty() && self.last_commit_forced {
            return ".".to_string();
        }
        typed
    }

    /// Whether the open window holds a voiced frame.
    fn window_has_voice(&self) -> bool {
        self.has_voice(0, self.window.len())
    }

    /// Whether `window[from..to]` holds a voiced frame.
    fn has_voice(&self, from: usize, to: usize) -> bool {
        let first = (self.window_start + from) / FRAME_SAMPLES;
        let last = (self.window_start + to).div_ceil(FRAME_SAMPLES);
        self.voiced
            .get(first..last.min(self.voiced.len()))
            .is_some_and(|frames| frames.iter().any(|&voiced| voiced))
    }

    /// With nothing pending, the audio before the last pause of at least
    /// [`COMMIT_PAUSE_S`] that speech follows is closed: no pass will ever
    /// agree on words in it. Without this a long pause would sit in the window
    /// and push the next sentence past [`MAX_WINDOW_S`]. Silence is released
    /// with no engine call; anything voiced (a cough, or quiet speech the timed
    /// pass heard nothing in) goes through the full default pipeline, fallback
    /// included, as a whole dictation would. Returns the text to type.
    fn close_before_pause(&mut self, pipeline: &mut Pipeline) -> Result<String, Error> {
        if !self.previous.is_empty() {
            return Ok(String::new());
        }
        let Some(pause_end) = self.last_pause_end() else {
            return Ok(String::new());
        };
        let lead_in = (LEADING_SILENCE_KEPT_S * SAMPLE_RATE as f32) as usize;
        let cut = pause_end.saturating_sub(lead_in).min(self.window.len());
        if cut == 0 {
            return Ok(String::new());
        }
        let text = if self.has_voice(0, cut) {
            pipeline.transcribe(&self.window[..cut])?.text
        } else {
            String::new()
        };
        self.release(cut);
        Ok(self.commit_text(&text, false))
    }

    /// Where (window samples) the latest run of at least [`COMMIT_PAUSE_S`] of
    /// unvoiced frames ends, when a voiced frame follows it.
    fn last_pause_end(&self) -> Option<usize> {
        let first = self.window_start.div_ceil(FRAME_SAMPLES);
        let frames = self.voiced.get(first..)?;
        let min_run = (COMMIT_PAUSE_S * SAMPLE_RATE as f32) as usize / FRAME_SAMPLES;
        let (mut run, mut end) = (0, None);
        for (i, &voiced) in frames.iter().enumerate() {
            if voiced {
                if run >= min_run {
                    end = Some(i);
                }
                run = 0;
            } else {
                run += 1;
            }
        }
        end.map(|frame| (first + frame) * FRAME_SAMPLES - self.window_start)
    }

    /// Drops the first `samples` of the window: they are committed.
    fn release(&mut self, samples: usize) {
        let samples = samples.min(self.window.len());
        self.window.drain(..samples);
        self.window_start += samples;
    }

    /// `text` as it is typed after what is committed: the first of a dictation
    /// as is, the others after a space, and after a commit cut mid-sentence
    /// with its first letter lowered (unless an acronym). Empty text changes nothing.
    fn commit_text(&mut self, text: &str, forced: bool) -> String {
        let text = text.trim();
        if text.is_empty() {
            return String::new();
        }
        let typed = if self.committed.is_empty() {
            text.to_string()
        } else if self.last_commit_forced {
            format!(" {}", lowercase_first(text))
        } else {
            format!(" {text}")
        };
        self.committed.push_str(&typed);
        self.last_commit_forced = forced;
        typed
    }
}

fn seconds(samples: usize) -> f32 {
    samples as f32 / SAMPLE_RATE as f32
}

fn joined(words: &[Word]) -> String {
    words
        .iter()
        .map(|word| word.text.as_str())
        .collect::<Vec<_>>()
        .join(" ")
}

fn ends_a_sentence(word: &str) -> bool {
    word.ends_with(['.', '?', '!', '…'])
}

/// The word, among the first `stable` and followed by another, after which the
/// gap is the largest (ties: the latest).
fn longest_gap(words: &[Word], stable: usize) -> Option<usize> {
    (0..stable.min(words.len().saturating_sub(1)))
        .map(|i| (i, words[i + 1].start_s - words[i].end_s))
        .fold(None, |best: Option<(usize, f32)>, (i, gap)| match best {
            Some((_, best_gap)) if gap < best_gap => best,
            _ => Some((i, gap)),
        })
        .map(|(i, _)| i)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Strategy, Transcriber};
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};

    type Timed = Box<dyn FnMut(&[f32]) -> Vec<Word> + Send>;
    type Plain = Box<dyn FnMut(&[f32]) -> String + Send>;

    const MAX_CALL: usize = (MAX_WINDOW_S * SAMPLE_RATE as f32) as usize;

    /// Lengths (samples) of the engine's calls, timed and plain.
    #[derive(Default)]
    struct Calls {
        timed: Vec<usize>,
        plain: Vec<usize>,
    }

    /// An engine whose answers are scripted by closures over the audio it gets.
    struct Fake {
        timed: Timed,
        plain: Plain,
        calls: Arc<Mutex<Calls>>,
    }

    impl Transcriber for Fake {
        fn name(&self) -> &'static str {
            "fake"
        }
        fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
            self.calls.lock().unwrap().plain.push(samples.len());
            Ok((self.plain)(samples))
        }
        fn transcribe_timed(&mut self, samples: &[f32]) -> Result<Option<Vec<Word>>, Error> {
            self.calls.lock().unwrap().timed.push(samples.len());
            Ok(Some((self.timed)(samples)))
        }
    }

    fn pipeline(timed: Timed, plain: Plain) -> (Pipeline, Arc<Mutex<Calls>>) {
        let calls = Arc::new(Mutex::new(Calls::default()));
        let fake = Fake {
            timed,
            plain,
            calls: calls.clone(),
        };
        (Pipeline::new(Box::new(fake), None, Strategy::Padded), calls)
    }

    /// Harmonic stack: reads as voiced to WebRTC VAD (see the `vad` tests).
    fn voiced(seconds: f32) -> Vec<f32> {
        let count = (seconds * SAMPLE_RATE as f32) as usize;
        (0..count)
            .map(|i| {
                let t = i as f32 / SAMPLE_RATE as f32;
                (1..=10)
                    .map(|h| 0.03 * (2.0 * std::f32::consts::PI * 150.0 * h as f32 * t).sin())
                    .sum::<f32>()
            })
            .collect()
    }

    fn silence(seconds: f32) -> Vec<f32> {
        vec![0.0; (seconds * SAMPLE_RATE as f32) as usize]
    }

    fn word(text: &str, start_s: f32, end_s: f32) -> Word {
        Word {
            text: text.to_string(),
            start_s,
            end_s,
        }
    }

    /// A scripted queue of hypotheses; the last one repeats when it runs out.
    fn queue(hypotheses: Vec<Vec<Word>>) -> Timed {
        let mut hypotheses = std::collections::VecDeque::from(hypotheses);
        let mut last = Vec::new();
        Box::new(move |_| {
            if let Some(next) = hypotheses.pop_front() {
                last = next;
            }
            last.clone()
        })
    }

    fn no_plain() -> Plain {
        Box::new(|_| String::new())
    }

    fn pass_now(streamer: &mut Streamer, pipeline: &mut Pipeline) -> Update {
        assert!(streamer.is_pass_due());
        streamer.pass(pipeline).unwrap()
    }

    fn seconds_of(samples: usize) -> f32 {
        samples as f32 / SAMPLE_RATE as f32
    }

    #[test]
    fn a_sentence_followed_by_speech_is_committed_after_two_agreeing_passes() {
        let hypothesis = vec![
            word("Je", 0.2, 0.5),
            word("vais", 0.6, 0.9),
            word("envoyer", 1.0, 1.5),
            word("le", 1.6, 1.8),
            word("rapport.", 1.9, 2.5),
            word("Pense", 3.0, 3.4),
        ];
        let (mut pipeline, calls) =
            pipeline(queue(vec![hypothesis.clone(), hypothesis]), no_plain());
        let mut streamer = Streamer::new();

        streamer.push(&voiced(4.0));
        let first = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(first.typed, "");
        assert_eq!(first.stats.stable, 0);
        assert_eq!(first.provisional, "Je vais envoyer le rapport. Pense");

        streamer.push(&voiced(0.6));
        let second = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(second.typed, "Je vais envoyer le rapport.");
        assert_eq!(second.provisional, "Pense");
        assert_eq!(second.stats.committed_words, 5);
        assert!(!second.stats.forced);
        assert_eq!(streamer.committed(), "Je vais envoyer le rapport.");

        // The window restarts in the middle of the gap (2.5 .. 3.0): 2.75 s are released.
        streamer.push(&voiced(0.6));
        pass_now(&mut streamer, &mut pipeline);
        let lengths = calls.lock().unwrap().timed.clone();
        assert_eq!(lengths[1], (4.6 * SAMPLE_RATE as f32) as usize);
        let expected = ((4.6 + 0.6 - 2.75) * SAMPLE_RATE as f32) as usize;
        assert!(lengths[2].abs_diff(expected) < 8, "{lengths:?}");
    }

    #[test]
    fn a_provisional_final_period_is_never_committed() {
        let short = vec![
            word("on", 0.2, 0.4),
            word("pourrait", 0.5, 1.0),
            word("faire.", 1.1, 1.5),
        ];
        let long = vec![
            word("on", 0.2, 0.4),
            word("pourrait", 0.5, 1.0),
            word("faire", 1.1, 1.5),
            word("vraiment", 1.6, 2.0),
            word("de", 2.1, 2.2),
            word("l'affichage.", 2.3, 3.0),
        ];
        let (mut pipeline, _) = pipeline(
            queue(vec![short.clone(), short, long.clone(), long]),
            no_plain(),
        );
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.7));
        for _ in 0..4 {
            let update = pass_now(&mut streamer, &mut pipeline);
            assert_eq!(update.typed, "");
            streamer.push(&voiced(0.6));
        }
        assert_eq!(streamer.committed(), "");
    }

    #[test]
    fn a_sentence_end_followed_by_two_seconds_of_silence_is_committed() {
        let hypothesis = vec![
            word("Bonjour", 0.2, 0.8),
            word("tout", 0.9, 1.1),
            word("le", 1.2, 1.3),
            word("monde.", 1.4, 1.5),
        ];
        let (mut pipeline, calls) = pipeline(queue(vec![hypothesis]), no_plain());
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.6));
        pass_now(&mut streamer, &mut pipeline);

        let mut typed = String::new();
        let mut silent_s = 0.0;
        while typed.is_empty() {
            streamer.push(&silence(0.6));
            silent_s += 0.6;
            typed = pass_now(&mut streamer, &mut pipeline).typed;
            assert!(silent_s < 5.0, "never committed");
        }
        // The sentence ends at 1.5 s; the window is 1.6 s of speech plus the silence.
        assert!(1.6 + silent_s - 1.5 >= COMMIT_PAUSE_S);
        assert!(1.6 + silent_s - 0.6 - 1.5 < COMMIT_PAUSE_S);
        assert_eq!(typed, "Bonjour tout le monde.");

        // Silence after everything is committed makes no engine call.
        let before = calls.lock().unwrap().timed.len();
        for _ in 0..100 {
            streamer.push(&silence(0.1));
            assert!(!streamer.is_pass_due());
        }
        streamer.pass(&mut pipeline).unwrap();
        let calls = calls.lock().unwrap();
        assert_eq!(calls.timed.len(), before);
        assert!(calls.plain.is_empty());
        // Only the lead-in is kept.
        assert!(seconds_of(streamer.window.len()) <= LEADING_SILENCE_KEPT_S + 1e-3);
    }

    /// Words of a run-on dictation at absolute times: 0.5 s apart, a 0.5 s gap
    /// after the twentieth. `Suite` is the twenty-first.
    fn run_on_words() -> Vec<Word> {
        (0..60)
            .map(|n| {
                let start = 0.5 * n as f32 + if n >= 20 { 0.4 } else { 0.0 };
                let text = match n {
                    20 => "Suite".to_string(),
                    _ => format!("m{n}"),
                };
                word(&text, start, start + 0.4)
            })
            .collect()
    }

    /// The run-on words inside the window, with window times; only those
    /// finished `margin_s` before the end of what was pushed.
    fn in_window(window_len: usize, pushed: &AtomicUsize, margin_s: f32) -> Vec<Word> {
        let pushed = seconds_of(pushed.load(Ordering::SeqCst));
        let offset = pushed - seconds_of(window_len);
        run_on_words()
            .into_iter()
            .filter(|w| w.start_s >= offset - 1e-3 && w.end_s <= pushed - margin_s)
            .map(|w| word(&w.text, w.start_s - offset, w.end_s - offset))
            .collect()
    }

    /// Streams `seconds` of speech in 0.6 s blocks, passing as the app does.
    /// `plain_answers`: whether the full pipeline hears the words or nothing.
    fn run_on(
        seconds: f32,
        plain_answers: bool,
    ) -> (Streamer, Pipeline, Arc<Mutex<Calls>>, Vec<Update>) {
        let pushed = Arc::new(AtomicUsize::new(0));
        let (for_timed, for_plain) = (pushed.clone(), pushed.clone());
        let (mut pipeline, calls) = pipeline(
            Box::new(move |window| in_window(window.len(), &for_timed, 0.2)),
            Box::new(move |window| {
                if plain_answers {
                    let words = in_window(window.len(), &for_plain, 0.0);
                    joined(&words)
                } else {
                    String::new()
                }
            }),
        );
        let mut streamer = Streamer::new();
        let mut updates = Vec::new();
        let blocks = (seconds / 0.6) as usize;
        for _ in 0..blocks {
            let block = voiced(0.6);
            pushed.fetch_add(block.len(), Ordering::SeqCst);
            streamer.push(&block);
            if streamer.is_pass_due() {
                updates.push(streamer.pass(&mut pipeline).unwrap());
            }
        }
        // What is left of `seconds`, too short for a pass.
        let rest = voiced(seconds - blocks as f32 * 0.6);
        pushed.fetch_add(rest.len(), Ordering::SeqCst);
        streamer.push(&rest);
        (streamer, pipeline, calls, updates)
    }

    #[test]
    fn run_on_speech_is_committed_by_fifteen_seconds_at_the_longest_gap() {
        let (streamer, mut pipeline, calls, updates) = run_on(25.0, true);
        let commits: Vec<&Update> = updates.iter().filter(|u| !u.typed.is_empty()).collect();
        assert_eq!(commits.len(), 1, "one forced commit");
        let commit = commits[0];
        assert!(commit.stats.forced);
        assert!(commit.stats.window_s >= FORCE_COMMIT_S);
        assert!(commit.stats.window_s < FORCE_COMMIT_S + PASS_EVERY_S + 0.1);
        // Cut after m19, before the 0.5 s gap: the longest.
        let head: Vec<String> = (0..20).map(|n| format!("m{n}")).collect();
        assert_eq!(commit.typed, head.join(" "));

        // The next text continues the sentence: lowered first letter.
        let committed = streamer.committed().to_string();
        let rest = streamer.finish(&mut pipeline).unwrap();
        assert!(rest.starts_with(" suite m21 "), "{rest}");
        // Every word once, in order, up to where the speech ends.
        let mut expected: Vec<String> = run_on_words()
            .into_iter()
            .filter(|w| w.end_s <= 25.0)
            .map(|w| w.text)
            .collect();
        expected[20] = "suite".to_string();
        assert_eq!(format!("{committed}{rest}"), expected.join(" "));

        let calls = calls.lock().unwrap();
        assert!(calls.timed.iter().all(|&len| len <= MAX_CALL));
        assert!(calls.plain.iter().all(|&len| len <= MAX_CALL));
    }

    #[test]
    fn finish_closes_a_forced_commit_with_a_period_when_nothing_follows() {
        let (streamer, mut pipeline, _, updates) = run_on(16.5, false);
        assert!(updates.iter().any(|u| u.stats.forced));
        assert!(!streamer.committed().is_empty());
        assert_eq!(streamer.finish(&mut pipeline).unwrap(), ".");
    }

    #[test]
    fn an_acronym_keeps_its_capitals_after_a_forced_commit() {
        let mut streamer = Streamer::new();
        assert_eq!(
            streamer.commit_text("On pousse sur la", true),
            "On pousse sur la"
        );
        assert_eq!(streamer.commit_text("API demain.", false), " API demain.");
        assert_eq!(streamer.commit_text("Merci.", false), " Merci.");
        let mut streamer = Streamer::new();
        streamer.commit_text("On pousse sur la", true);
        assert_eq!(streamer.commit_text("Dernière", false), " dernière");
        assert_eq!(streamer.committed(), "On pousse sur la dernière");
    }

    #[test]
    fn an_overflowing_window_is_committed_whole_through_the_pipeline() {
        let (mut pipeline, calls) = pipeline(
            Box::new(|_| panic!("the timed call must not receive an overflowing window")),
            Box::new(|_| "alpha beta".to_string()),
        );
        let mut streamer = Streamer::new();
        streamer.push(&voiced(25.0));
        let update = pass_now(&mut streamer, &mut pipeline);
        assert!(update.stats.forced);
        assert_eq!(update.typed, "alpha beta alpha beta");
        assert_eq!(update.stats.committed_words, 4);
        assert_eq!(streamer.window.len(), 0);
        let calls = calls.lock().unwrap();
        assert!(calls.timed.is_empty());
        assert!(!calls.plain.is_empty());
        assert!(calls.plain.iter().all(|&len| len <= MAX_CALL));
    }

    #[test]
    fn leading_silence_costs_no_engine_call() {
        let (mut pipeline, calls) = pipeline(queue(vec![]), no_plain());
        let mut streamer = Streamer::new();
        for _ in 0..30 {
            streamer.push(&silence(0.5));
            assert!(!streamer.is_pass_due());
        }
        assert_eq!(streamer.finish(&mut pipeline).unwrap(), "");
        let calls = calls.lock().unwrap();
        assert!(calls.timed.is_empty() && calls.plain.is_empty());
    }

    #[test]
    fn finish_joins_with_a_space_after_a_sentence_commit() {
        let hypothesis = vec![word("Bonjour.", 0.2, 0.9), word("Ça", 1.2, 1.4)];
        let (mut pipeline, _) = pipeline(
            queue(vec![hypothesis.clone(), hypothesis]),
            Box::new(|_| "Ça va ?".to_string()),
        );
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.6));
        pass_now(&mut streamer, &mut pipeline);
        streamer.push(&voiced(0.6));
        let update = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(update.typed, "Bonjour.");
        assert_eq!(streamer.finish(&mut pipeline).unwrap(), " Ça va ?");
    }

    #[test]
    fn an_engine_without_timings_only_commits_by_overflow() {
        struct Untimed;
        impl Transcriber for Untimed {
            fn name(&self) -> &'static str {
                "untimed"
            }
            fn transcribe(&mut self, _: &[f32]) -> Result<String, Error> {
                Ok("mot".to_string())
            }
        }
        let mut pipeline = Pipeline::new(Box::new(Untimed), None, Strategy::Padded);
        let mut streamer = Streamer::new();
        streamer.push(&voiced(3.0));
        let update = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(update.typed, "");
        assert_eq!(update.stats.words, 0);
        assert_eq!(streamer.finish(&mut pipeline).unwrap(), "mot");
    }

    /// Commits « Bonjour. » with a 2 s pause, as the user stops talking.
    fn after_a_committed_sentence(pipeline: &mut Pipeline) -> Streamer {
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.0));
        pass_now(&mut streamer, pipeline);
        let mut typed = String::new();
        while typed.is_empty() {
            streamer.push(&silence(0.6));
            typed = pass_now(&mut streamer, pipeline).typed;
        }
        assert_eq!(typed, "Bonjour.");
        streamer
    }

    #[test]
    fn a_long_pause_never_pushes_the_next_sentence_into_an_overflow() {
        let (mut pipeline, calls) = pipeline(
            // Five passes commit « Bonjour. » (see `after_a_committed_sentence`).
            queue(
                std::iter::repeat_n(vec![word("Bonjour.", 0.2, 0.9)], 5)
                    .chain([vec![word("Ensuite", 0.5, 1.0)]])
                    .collect(),
            ),
            no_plain(),
        );
        let mut streamer = after_a_committed_sentence(&mut pipeline);
        // 25 s of thinking: no pass is due, the window grows.
        for _ in 0..50 {
            streamer.push(&silence(0.5));
            assert!(!streamer.is_pass_due());
        }
        streamer.push(&voiced(1.0));
        let update = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(update.typed, "");
        assert_eq!(update.provisional, "Ensuite");
        assert!(!update.stats.forced);
        let calls = calls.lock().unwrap();
        // The pause was released with no engine call: the timed pass saw the
        // lead-in and the new speech only, and the full pipeline never ran.
        let last = seconds_of(*calls.timed.last().unwrap());
        assert!(last <= LEADING_SILENCE_KEPT_S + 1.0 + 0.1, "{last} s");
        assert!(calls.plain.is_empty());
    }

    #[test]
    fn a_sound_with_no_words_before_a_long_pause_goes_through_the_full_pipeline() {
        // Words only once a full second of speech ends the window.
        let timed: Timed = Box::new(|samples| {
            let second = SAMPLE_RATE as usize;
            let tail = &samples[samples.len().saturating_sub(second)..];
            // The louder copy removes the mean: silence is near zero, not zero.
            let loudness = tail.iter().map(|s| s.abs()).sum::<f32>() / tail.len().max(1) as f32;
            let is_speaking = samples.len() > second && loudness > 0.01;
            let start = seconds_of(samples.len()) - 1.0;
            if is_speaking {
                vec![word("Ensuite", start + 0.1, start + 0.6)]
            } else {
                vec![]
            }
        });
        let (mut pipeline, calls) = pipeline(timed, Box::new(|_| "Oui.".to_string()));
        let mut streamer = Streamer::new();
        // Quiet speech the timed pass hears nothing in, then a long pause.
        streamer.push(&voiced(0.6));
        let first = pass_now(&mut streamer, &mut pipeline);
        assert_eq!((first.typed.as_str(), first.stats.words), ("", 0));
        // The VAD's hangover may call for a pass or two: they hear nothing.
        for _ in 0..50 {
            streamer.push(&silence(0.5));
            if streamer.is_pass_due() {
                assert_eq!(streamer.pass(&mut pipeline).unwrap().typed, "");
            }
        }
        streamer.push(&voiced(1.0));
        let update = pass_now(&mut streamer, &mut pipeline);
        // The full pipeline (fallback included) gave it a text, typed now.
        assert_eq!(update.typed, "Oui.");
        assert_eq!(calls.lock().unwrap().plain.len(), 1);
        streamer.push(&voiced(0.6));
        let next = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(next.provisional, "Ensuite");
        let last = seconds_of(*calls.lock().unwrap().timed.last().unwrap());
        assert!(last <= LEADING_SILENCE_KEPT_S + 1.6 + 0.1, "{last} s");
    }

    #[test]
    fn stable_words_with_no_sentence_end_are_committed_after_a_long_pause() {
        let hypothesis = vec![word("ok", 0.2, 0.5), word("alors", 0.6, 1.0)];
        let (mut pipeline, calls) = pipeline(queue(vec![hypothesis]), no_plain());
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.2));
        pass_now(&mut streamer, &mut pipeline);
        let mut update = Update::default();
        while update.typed.is_empty() {
            streamer.push(&silence(0.6));
            update = pass_now(&mut streamer, &mut pipeline);
        }
        assert_eq!(update.typed, "ok alors");
        assert!(update.stats.forced);
        // Then the silence costs nothing, and what follows continues the sentence.
        let before = calls.lock().unwrap().timed.len();
        for _ in 0..20 {
            streamer.push(&silence(0.5));
            assert!(!streamer.is_pass_due());
        }
        assert_eq!(calls.lock().unwrap().timed.len(), before);
        assert_eq!(streamer.finish_with("On y va."), " on y va.");
    }

    #[test]
    fn rest_and_finish_with_match_finish() {
        let (mut pipeline, _) = pipeline(
            queue(vec![vec![word("Bonjour.", 0.2, 0.9)]]),
            Box::new(|_| "Ça va ?".to_string()),
        );
        let mut streamer = after_a_committed_sentence(&mut pipeline);
        streamer.push(&voiced(1.0));
        let rest = streamer.rest().to_vec();
        let text = pipeline.transcribe(&rest).unwrap().text;
        assert_eq!(streamer.finish_with(&text), " Ça va ?");
    }
}

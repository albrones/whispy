//! Rolling re-transcription: type what is said while it is said, with the
//! quality of one block (V2's « Type while speaking »).
//!
//! The pieces of [`crate::split::LiveSplitter`] decide at a pause, with no
//! context, and cannot take it back. This is « LocalAgreement » (Macháček et
//! al., 2023) over NVIDIA's buffered Parakeet inference: the window, a few
//! seconds already typed then the open audio, is re-transcribed with word
//! times every [`PASS_EVERY_S`]. A word is committed once two consecutive
//! passes agree on it, word for word from the start of the open text, and the
//! model has heard [`LOOKAHEAD_S`] of audio past it while more words follow
//! ([`COMMIT_PAUSE_S`] of silence when none does). Its punctuation is decided
//! with that much right context: a thinking pause leaves a period open until
//! the model has heard what comes next.
//!
//! After a commit the window keeps [`LEFT_CONTEXT_S`] of the typed audio,
//! starting in a gap between words, and the words a pass hears in it are
//! dropped (they are typed already). The model hears the open text inside its
//! sentence, so a commit may fall anywhere. The bench measured the first
//! version, which committed at sentence ends with one word of right context
//! and restarted each window cold: on the user's dictations it typed periods
//! where one block has commas (« comportement. Déjà ») and misheard words
//! after a cut (« ça aurait ‖ c'était ‖ beaucoup »).
//!
//! No engine call gets more than [`MAX_WINDOW_S`]: past it, the open audio
//! goes whole through the default pipeline. Every pushed sample ends in
//! exactly one committed text or in the stop's ([`Streamer::finish`]);
//! silence nobody spoke over is dropped.
//!
//! A [`Streamer`] holds a [`VoiceDetector`] (a raw C pointer): like
//! [`crate::split::LiveSplitter`] it is not `Send`; create it on the thread
//! that drives it. No dictated text is ever logged here: [`PassStats`] is counts.

use std::time::Instant;

use crate::audio::SAMPLE_RATE;
use crate::itn;
use crate::join::lowercase_first;
use crate::split::MAX_PIECE_S;
use crate::vad::{VoiceDetector, FRAME_SAMPLES};
use crate::{Error, Pipeline, Strategy, Word};

/// New audio, in seconds, between two passes.
pub const PASS_EVERY_S: f32 = 0.6;
/// Audio the model must have heard past a word, more words following, before
/// the word is committed: the right context its punctuation is decided with.
pub const LOOKAHEAD_S: f32 = 1.5;
/// Words that must follow a word before it is committed (with
/// [`LOOKAHEAD_S`]): a thinking pause fills the seconds, not the words, and
/// the bench saw « dernière. Mais » typed where one block has « dernière, mais ».
pub const LOOKAHEAD_WORDS: usize = 3;
/// Fewest words typed at once, unless they end on punctuation or a pause:
/// each commit is a paste (about half a second, and the clipboard swapped).
pub const MIN_COMMIT_WORDS: usize = 4;
/// Audio heard past the first open word after which the last pass is trusted
/// alone (#72): no agreement, one word after (not [`LOOKAHEAD_WORDS`]), any
/// passage worth a paste. Agreement from the first open word can fail for many
/// passes in a row (a word heard two ways, a comma that comes and goes), and
/// slow speech can take seconds to bring three more words: on the user's
/// dictations whole sentences landed at once, up to ten seconds late. Each
/// word is still heard [`LOOKAHEAD_S`] past (the pause: [`COMMIT_PAUSE_S`]).
pub const PATIENCE_S: f32 = 3.0;
/// A gap between two heard words this long may hold speech the pass has not
/// transcribed yet (« sans ça. ‖ Euh... ça aurait ‖ été »): a commit without
/// agreement stops before it.
const UNHEARD_GAP_S: f32 = 1.0;
/// Silence after the last word heard that commits it.
pub const COMMIT_PAUSE_S: f32 = 2.0;
/// Typed audio kept before the open audio, so the model hears it in context.
pub const LEFT_CONTEXT_S: f32 = 5.0;
/// No engine call gets more than this: past it the open audio is committed whole.
pub const MAX_WINDOW_S: f32 = MAX_PIECE_S;
/// A window this long is committed whole: two passes early, so the overflow
/// call itself stays one piece under [`MAX_WINDOW_S`] (the pipeline would
/// otherwise split it and hear a short tail on its own).
const OVERFLOW_S: f32 = MAX_WINDOW_S - 2.0 * PASS_EVERY_S;
/// What is kept of open audio that holds no voice and no hypothesis: the start
/// of the next word needs its lead-in.
pub const LEADING_SILENCE_KEPT_S: f32 = 0.5;
/// How far past the last committed word the context ends. Not the middle of
/// the gap to the next word heard: speech the pass did not transcribe yet may
/// sit in that gap (the bench lost « Euh... ça aurait » between « ça. » and
/// « été » that way), and it must stay open to be heard again.
const BOUNDARY_MARGIN_S: f32 = 0.15;

/// What one pass did. Counts only, never text: it goes to the log.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct PassStats {
    /// The window's length (context included) when the pass began.
    pub window_s: f32,
    /// Time spent in the engine.
    pub took_s: f32,
    /// Words of the new hypothesis after the context.
    pub words: usize,
    /// Words it shares with the previous hypothesis, from the start.
    pub stable: usize,
    pub committed_words: usize,
    /// The open audio was committed whole, without word times (overflow).
    pub forced: bool,
    /// Where the committed text's audio ends, in seconds since the stream
    /// began (its last word's end, or the released audio's end when the text
    /// has no timings); 0 when nothing was committed. The bench's commit delay.
    pub audio_end_s: f32,
    /// How long the oldest word typed by this pass waited: from the end of
    /// its audio to the end of the pass, in audio seconds; 0 when nothing was
    /// typed. A passage is pasted at once, so this is what the speaker waits
    /// for its first word (`audio_end_s` dates its last word).
    pub waited_s: f32,
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

/// The stop's outcome.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Finish {
    /// Text to append to the field, already joined; may be empty.
    pub typed: String,
    /// The engine that gave it, `None` when it is empty.
    pub engine: Option<&'static str>,
    /// The open audio, when the gates call it speech and no text came back:
    /// the app keeps it as a lost clip for the bench.
    pub lost: Option<Vec<f32>>,
}

pub struct Streamer {
    /// The left context, then the open audio.
    window: Vec<f32>,
    /// Samples since the last complete VAD frame.
    frame_tail: Vec<f32>,
    detector: VoiceDetector,
    /// One voiced flag per VAD frame since the stream began.
    voiced: Vec<bool>,
    /// Where the window starts, in samples since the stream began.
    window_start: usize,
    /// Samples at the start of the window that are typed already.
    context: usize,
    pushed_since_pass: usize,
    voiced_since_pass: bool,
    /// The last hypothesis after the context, times relative to the window.
    previous: Vec<Word>,
    /// The committed text as the engine wrote it, passages joined.
    raw: String,
    /// What has been returned as typed: [`itn::normalize`] of the stable
    /// prefix of `raw`.
    shown: String,
    /// [`itn::normalize`] of all of `raw`, for the caption.
    committed: String,
    /// Words (as the engine wrote them) of the last text committed.
    last_words: usize,
    /// Per committed word not typed yet: where it ends in `raw` (bytes) and
    /// where its audio ends (seconds since the stream began).
    untyped_ends: Vec<(usize, f32)>,
    /// Audio end of the oldest word the last [`Streamer::release_typed`]
    /// typed, `None` when it typed nothing.
    oldest_typed_end_s: Option<f32>,
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
            context: 0,
            pushed_since_pass: 0,
            voiced_since_pass: false,
            previous: Vec::new(),
            raw: String::new(),
            shown: String::new(),
            committed: String::new(),
            last_words: 0,
            untyped_ends: Vec::new(),
            oldest_typed_end_s: None,
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

    /// Everything committed so far, numbers in digits: what the field holds,
    /// plus a number still being spoken that is held back.
    pub fn committed(&self) -> &str {
        &self.committed
    }

    /// The open audio: what is not typed yet.
    pub fn rest(&self) -> &[f32] {
        &self.window[self.context..]
    }

    /// One re-transcription of the window; commits what is stable.
    pub fn pass(&mut self, pipeline: &mut Pipeline) -> Result<Update, Error> {
        let heard_s = seconds(self.window_start + self.window.len());
        let started = Instant::now();
        self.oldest_typed_end_s = None;
        let mut update = self.pass_inner(pipeline)?;
        if let Some(end_s) = self.oldest_typed_end_s.take() {
            if !update.typed.is_empty() {
                let ended_s = heard_s + started.elapsed().as_secs_f32();
                update.stats.waited_s = (ended_s - end_s).max(0.0);
            }
        }
        Ok(update)
    }

    fn pass_inner(&mut self, pipeline: &mut Pipeline) -> Result<Update, Error> {
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
            stats.committed_words = self.last_words;
            stats.audio_end_s = seconds(self.window_start);
            return Ok(Update {
                typed: closed,
                provisional: String::new(),
                stats,
            });
        }

        // 1. Nothing said and nothing pending: keep only the lead-in.
        if self.previous.is_empty() && !self.has_voice(self.context, self.window.len()) {
            let kept = (LEADING_SILENCE_KEPT_S * SAMPLE_RATE as f32) as usize;
            self.release(self.window.len().saturating_sub(kept));
            self.context = 0;
            return Ok(Update {
                stats,
                ..Update::default()
            });
        }

        // 2. Overflow: the open audio through the full default pipeline, committed whole.
        if window_s > OVERFLOW_S {
            let started = Instant::now();
            let text = pipeline.transcribe_raw(self.rest())?.text;
            stats.took_s = started.elapsed().as_secs_f32();
            let end_s = seconds(self.window_start + self.window.len());
            let typed = self.commit_text(&text, &[end_s], false, false);
            self.release(self.window.len());
            self.previous.clear();
            stats.committed_words = self.last_words;
            stats.forced = true;
            stats.audio_end_s = seconds(self.window_start);
            return Ok(Update {
                typed,
                provisional: String::new(),
                stats,
            });
        }

        // 3. The hypothesis; the words heard in the context are typed already.
        // An engine without timings never agrees with itself.
        let started = Instant::now();
        let heard = pipeline.transcribe_timed(&self.window)?.unwrap_or_default();
        stats.took_s = started.elapsed().as_secs_f32();
        let in_context = self.context > 0;
        let first_open = first_after(&heard, seconds(self.context));
        let open = &heard[first_open..];
        stats.words = open.len();

        // 4. The words two passes agree on, punctuation and case included.
        let stable = open
            .iter()
            .zip(&self.previous)
            .take_while(|(new, old)| new.text == old.text)
            .count();
        stats.stable = stable;
        // 5. The last stable word the model has heard far enough past that
        // makes a passage worth a paste: enough words, or the end of a phrase,
        // or the last word before a pause.
        //
        // Once the first open word was heard PATIENCE_S ago, this pass, which
        // heard the most, is trusted alone: agreement is waived, one word after (or the pause)
        // is enough, and any passage is worth a paste. Not across a gap of
        // UNHEARD_GAP_S between two words: speech this pass did not transcribe
        // may sit there, and committing past it would drop it in the context.
        let impatient = open
            .first()
            .is_some_and(|first| window_s - first.end_s >= PATIENCE_S);
        let trusted = if impatient {
            (1..open.len())
                .find(|&k| open[k].start_s - open[k - 1].end_s >= UNHEARD_GAP_S)
                .unwrap_or(open.len())
        } else {
            0
        };
        let commit = (0..stable.max(trusted)).rev().find(|&i| {
            let heard_past = window_s - open[i].end_s;
            let words_after = open.len() - i - 1;
            if i < trusted {
                return heard_past >= LOOKAHEAD_S
                    && (words_after > 0 || heard_past >= COMMIT_PAUSE_S);
            }
            let is_heard_past = if words_after == 0 {
                heard_past >= COMMIT_PAUSE_S
            } else {
                heard_past >= LOOKAHEAD_S && words_after >= LOOKAHEAD_WORDS
            };
            let is_worth_a_paste = i + 1 >= MIN_COMMIT_WORDS
                || words_after == 0
                || open[i].text.ends_with(['.', ',', '?', '!', '…', ';', ':']);
            is_heard_past && is_worth_a_paste
        });
        let Some(i) = commit else {
            let provisional = itn::normalize(&joined(open));
            self.previous = open.to_vec();
            return Ok(Update {
                typed: String::new(),
                provisional,
                stats,
            });
        };

        // 6. Commit; the window keeps LEFT_CONTEXT_S before the boundary.
        let gap_middle = open
            .get(i + 1)
            .map_or(window_s, |next| (open[i].end_s + next.start_s) / 2.0);
        let boundary_s = (open[i].end_s + BOUNDARY_MARGIN_S)
            .min(gap_middle)
            .min(window_s);
        stats.audio_end_s = seconds(self.window_start) + open[i].end_s;
        let ends: Vec<f32> = open[..=i]
            .iter()
            .map(|word| seconds(self.window_start) + word.end_s)
            .collect();
        let typed = self.commit_text(&joined(&open[..=i]), &ends, in_context, false);
        stats.committed_words = self.last_words;
        let start_s = context_start(&heard[..=first_open + i], boundary_s - LEFT_CONTEXT_S);
        let start = (start_s * SAMPLE_RATE as f32) as usize;
        let boundary = (boundary_s * SAMPLE_RATE as f32) as usize;
        let mut rest = open[i + 1..].to_vec();
        for word in &mut rest {
            word.start_s = (word.start_s - start_s).max(0.0);
            word.end_s = (word.end_s - start_s).max(0.0);
        }
        self.release(start);
        self.context = boundary.saturating_sub(start).min(self.window.len());
        let provisional = itn::normalize(&joined(&rest));
        self.previous = rest;
        Ok(Update {
            typed,
            provisional,
            stats,
        })
    }

    /// The stop: the open audio is transcribed once more, in its context when
    /// there is one (Parakeet with times, the context's words dropped), else,
    /// or when that hears nothing, through the full default pipeline (gates,
    /// padding, fallback, 20 s split).
    pub fn finish(mut self, pipeline: &mut Pipeline) -> Result<Finish, Error> {
        let open = self.rest().to_vec();
        let (text, engine, in_context) = match self.hear_open(pipeline, &open) {
            Ok(heard) => heard,
            Err(error) => {
                // A number held back is still the speaker's: type it, and keep
                // the audio the engine failed on as a lost clip.
                let typed = self.release_typed(true);
                if typed.is_empty() {
                    return Err(error);
                }
                let is_speech = Strategy::Gated.prepare(&open).is_some();
                return Ok(Finish {
                    typed,
                    engine: None,
                    lost: is_speech.then_some(open),
                });
            }
        };
        let is_lost = text.trim().is_empty() && Strategy::Gated.prepare(&open).is_some();
        let end_s = seconds(self.window_start + self.window.len());
        let typed = self.commit_text(&text, &[end_s], in_context, true);
        Ok(Finish {
            engine: engine.filter(|_| !typed.is_empty()),
            typed,
            lost: is_lost.then_some(open),
        })
    }

    /// What the stop types, without a number held back: the text of the open
    /// audio, the engine that gave it, and whether it was heard in context.
    fn hear_open(
        &self,
        pipeline: &mut Pipeline,
        open: &[f32],
    ) -> Result<(String, Option<&'static str>, bool), Error> {
        if self.context > 0 && !open.is_empty() {
            let heard = pipeline.transcribe_timed(&self.window)?.unwrap_or_default();
            let words = &heard[first_after(&heard, seconds(self.context))..];
            if !words.is_empty() {
                return Ok((joined(words), Some(pipeline.primary_name()), true));
            }
        }
        let transcript = pipeline.transcribe_raw(open)?;
        Ok((transcript.text, transcript.engine, false))
    }

    /// The stop with nothing to transcribe (a deaf take, no engine loaded):
    /// what a number held back says, typed now.
    pub fn flush(mut self) -> String {
        self.release_typed(true)
    }

    /// Whether `window[from..to]` holds a voiced frame.
    fn has_voice(&self, from: usize, to: usize) -> bool {
        let first = (self.window_start + from) / FRAME_SAMPLES;
        let last = (self.window_start + to).div_ceil(FRAME_SAMPLES);
        self.voiced
            .get(first..last.min(self.voiced.len()))
            .is_some_and(|frames| frames.iter().any(|&voiced| voiced))
    }

    /// With nothing pending, the open audio before the last pause of at least
    /// [`COMMIT_PAUSE_S`] that speech follows is closed: no pass will ever
    /// agree on words in it. Without this a long pause would sit in the window
    /// and push the next sentence past [`MAX_WINDOW_S`]. Silence is released
    /// with no engine call; anything voiced (a cough, or quiet speech the timed
    /// pass heard nothing in) goes through the full default pipeline, fallback
    /// included, as a whole dictation would. The context goes with it: what
    /// follows a long pause is heard on its own. Returns the text to type.
    fn close_before_pause(&mut self, pipeline: &mut Pipeline) -> Result<String, Error> {
        if !self.previous.is_empty() {
            return Ok(String::new());
        }
        let Some(pause_end) = self.last_pause_end() else {
            return Ok(String::new());
        };
        let lead_in = (LEADING_SILENCE_KEPT_S * SAMPLE_RATE as f32) as usize;
        let cut = pause_end
            .saturating_sub(lead_in)
            .clamp(self.context, self.window.len());
        if cut == 0 {
            return Ok(String::new());
        }
        let text = if self.has_voice(self.context, cut) {
            pipeline
                .transcribe_raw(&self.window[self.context..cut])?
                .text
        } else {
            String::new()
        };
        self.release(cut);
        self.context = 0;
        let end_s = seconds(self.window_start);
        Ok(self.commit_text(&text, &[end_s], false, false))
    }

    /// Where (window samples) the latest run of at least [`COMMIT_PAUSE_S`] of
    /// unvoiced frames in the open audio ends, when a voiced frame follows it.
    fn last_pause_end(&self) -> Option<usize> {
        let first = (self.window_start + self.context).div_ceil(FRAME_SAMPLES);
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

    /// Drops the first `samples` of the window.
    fn release(&mut self, samples: usize) {
        let samples = samples.min(self.window.len());
        self.window.drain(..samples);
        self.window_start += samples;
        self.context = self.context.saturating_sub(samples);
    }

    /// `text` as it is typed after what is committed: the first of a dictation
    /// as is, the others after a space. After a typed `.`, `?` or `!`, its
    /// first letter is raised: that period may come from an earlier pass than
    /// the text, which did not hear it (« donc bon. pensez »). Heard without
    /// context after a text that ends mid-sentence, its first letter is
    /// lowered (unless an acronym); in context the model's own case stands (a
    /// proper noun mid-sentence). Returns what the field gets now (see `release_typed`).
    ///
    /// `ends` dates the words' audio (seconds since the stream began): one per
    /// word, or one for them all (a text with no timings).
    fn commit_text(&mut self, text: &str, ends: &[f32], in_context: bool, flush: bool) -> String {
        let text = text.trim();
        self.last_words = 0;
        if !text.is_empty() {
            let before = self.raw.trim_end();
            let continues = !before.is_empty() && !ends_a_sentence(before);
            let text = if ends_a_statement(before) {
                uppercase_first(text)
            } else if continues && !in_context {
                lowercase_first(text)
            } else {
                text.to_string()
            };
            if !self.raw.is_empty() {
                self.raw.push(' ');
            }
            let base = self.raw.len();
            self.raw.push_str(&text);
            let words: Vec<(usize, &str)> = text
                .split_whitespace()
                .map(|word| (word.as_ptr() as usize - text.as_ptr() as usize, word))
                .collect();
            self.last_words = words.len();
            let fallback = ends.last().copied().unwrap_or(0.0);
            for (k, (offset, word)) in words.iter().enumerate() {
                let end_s = if ends.len() == words.len() {
                    ends[k]
                } else {
                    fallback
                };
                self.untyped_ends.push((base + offset + word.len(), end_s));
            }
        }
        self.release_typed(flush)
    }

    /// What the field gets now: [`itn::normalize`] of the committed text, minus
    /// what it has been given. A number still being spoken (see
    /// [`itn::stable_prefix_len`]) waits for what follows, unless `flush`: the
    /// stop types everything. Normalising the stable prefix always gives the
    /// start of normalising the whole, so the passages joined equal one block.
    fn release_typed(&mut self, flush: bool) -> String {
        let stable = if flush {
            self.raw.len()
        } else {
            itn::stable_prefix_len(&self.raw)
        };
        let typed_words = self
            .untyped_ends
            .iter()
            .take_while(|(end, _)| *end <= stable)
            .count();
        if let Some(&(_, end_s)) = self.untyped_ends.first().filter(|_| typed_words > 0) {
            self.oldest_typed_end_s = Some(end_s);
        }
        self.untyped_ends.drain(..typed_words);
        let target = itn::normalize(&self.raw[..stable]);
        self.committed = itn::normalize(&self.raw);
        // Never retype: what the field holds stays, only what extends it is typed.
        let typed = target
            .get(self.shown.len()..)
            .unwrap_or_default()
            .to_string();
        debug_assert!(
            target.starts_with(self.shown.as_str()),
            "typed text changed"
        );
        self.shown.push_str(&typed);
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

fn ends_a_sentence(text: &str) -> bool {
    text.ends_with(['.', '?', '!', '…'])
}

/// A sentence end after which a capital follows: not an ellipsis, which in
/// French may go on in lowercase (« sera de... pouvoir »).
fn ends_a_statement(text: &str) -> bool {
    text.ends_with(['.', '?', '!']) && !text.ends_with("..")
}

fn uppercase_first(text: &str) -> String {
    let mut chars = text.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().chain(chars).collect(),
        None => String::new(),
    }
}

/// The index of the first word whose middle is at or past `context_s`: the
/// words before it were heard in the context, which is typed already.
fn first_after(words: &[Word], context_s: f32) -> usize {
    words
        .iter()
        .position(|word| (word.start_s + word.end_s) / 2.0 >= context_s)
        .unwrap_or(words.len())
}

/// Where the window should start to keep about `target_s` onwards as context,
/// in a gap between `words` (the words up to the boundary) so no word is cut:
/// `target_s` itself when it falls in a gap, else the middle of the gap before
/// the first word that starts after it. 0 keeps the whole window.
fn context_start(words: &[Word], target_s: f32) -> f32 {
    if target_s <= 0.0 {
        return 0.0;
    }
    match words.iter().position(|word| word.start_s >= target_s) {
        Some(k) if k > 0 && target_s < words[k - 1].end_s => {
            (words[k - 1].end_s + words[k].start_s) / 2.0
        }
        _ => target_s,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Transcriber;
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

    // --- an engine that hears the audio it is given ------------------------

    /// Word `k` of a [`spoken`] dictation lasts `0.3 + 0.04 k` seconds.
    fn word_seconds(k: usize) -> f32 {
        0.3 + 0.04 * k as f32
    }

    /// Voiced words separated by silence; `pauses[k]` follows word `k`.
    fn spoken(pauses: &[f32]) -> Vec<f32> {
        let mut audio = silence(0.3);
        for (k, pause) in pauses.iter().enumerate() {
            audio.extend(voiced(word_seconds(k)));
            audio.extend(silence(*pause));
        }
        audio
    }

    /// The voiced runs of `samples` (10 ms frames), as (start, end) seconds.
    fn runs(samples: &[f32]) -> Vec<(f32, f32)> {
        let frame = SAMPLE_RATE as usize / 100;
        let mut runs = Vec::new();
        let mut start = None;
        for (i, chunk) in samples.chunks(frame).enumerate() {
            let loud = chunk.iter().map(|s| s.abs()).sum::<f32>() / chunk.len() as f32 > 0.02;
            match (loud, start) {
                (true, None) => start = Some(i),
                (false, Some(s)) => {
                    runs.push((s as f32 / 100.0, i as f32 / 100.0));
                    start = None;
                }
                _ => {}
            }
        }
        if let Some(s) = start {
            runs.push((
                s as f32 / 100.0,
                samples.len().div_ceil(frame) as f32 / 100.0,
            ));
        }
        runs
    }

    /// Names each voiced run by its length (`w<k>`, see [`word_seconds`]); a
    /// run cut by the window's start gets a wrong name, as a real engine
    /// mishears a clipped word. A run still going at the window's end is left
    /// out: the speaker is in the middle of it.
    fn hear(samples: &[f32]) -> Vec<Word> {
        let end_s = seconds_of(samples.len());
        runs(samples)
            .into_iter()
            .filter(|&(_, end)| end < end_s - 0.05)
            .map(|(start, end)| {
                let k = ((end - start - 0.3) / 0.04).round().max(0.0) as usize;
                word(&format!("w{k}"), start, end)
            })
            .collect()
    }

    fn hearing_pipeline() -> (Pipeline, Arc<Mutex<Calls>>) {
        pipeline(
            Box::new(hear),
            Box::new(|samples| {
                hear(samples)
                    .iter()
                    .map(|w| w.text.clone())
                    .collect::<Vec<_>>()
                    .join(" ")
            }),
        )
    }

    /// Plays `audio` to a streamer 50 ms at a time with a pass whenever one is
    /// due, then stops; returns the typed text and every update.
    fn dictate(audio: &[f32], pipeline: &mut Pipeline) -> (String, Vec<Update>) {
        let mut streamer = Streamer::new();
        let mut updates = Vec::new();
        for block in audio.chunks(800) {
            streamer.push(block);
            if streamer.is_pass_due() {
                updates.push(streamer.pass(pipeline).unwrap());
            }
        }
        let mut text: String = updates.iter().map(|u| u.typed.as_str()).collect();
        text.push_str(&streamer.finish(pipeline).unwrap().typed);
        (text, updates)
    }

    fn expected_words(count: usize) -> String {
        (0..count)
            .map(|k| format!("w{k}"))
            .collect::<Vec<_>>()
            .join(" ")
    }

    #[test]
    fn every_word_is_typed_once_in_order_with_no_call_over_twenty_seconds() {
        // 30 words, a 1 s pause every 7 (no sentence ends: commits fall mid-speech).
        let pauses: Vec<f32> = (0..30)
            .map(|k| if k % 7 == 6 { 1.0 } else { 0.15 })
            .collect();
        let audio = spoken(&pauses);
        let (mut pipeline, calls) = hearing_pipeline();
        let (text, updates) = dictate(&audio, &mut pipeline);
        assert_eq!(text, expected_words(30));
        let commits = updates.iter().filter(|u| !u.typed.is_empty()).count();
        assert!(
            commits >= 5,
            "{commits} commits: text must flow while spoken"
        );
        let calls = calls.lock().unwrap();
        assert!(calls
            .timed
            .iter()
            .chain(&calls.plain)
            .all(|&n| n <= MAX_CALL));
        // Words flow out of the window: it never grows into an overflow.
        assert!(updates.iter().all(|u| !u.stats.forced));
        let longest = seconds_of(*calls.timed.iter().max().unwrap());
        assert!(longest < OVERFLOW_S, "longest window {longest} s");
    }

    /// The longest a typed word waited across `updates`, seconds.
    fn longest_wait(updates: &[Update]) -> f32 {
        updates.iter().map(|u| u.stats.waited_s).fold(0.0, f32::max)
    }

    /// Bound on any word's wait when passes are instant: PATIENCE_S, plus up
    /// to one pass interval before a pass sees it, plus a 10 ms frame.
    const WAIT_BOUND_S: f32 = PATIENCE_S + PASS_EVERY_S + 0.05;

    #[test]
    fn a_hypothesis_that_never_agrees_is_still_typed_within_patience() {
        // #72: every other pass hears a comma after each word, so two passes
        // never agree from the first open word. Before PATIENCE_S, nothing was
        // typed until the window overflowed (about 17 s) or the stop.
        let pauses = vec![0.15; 30];
        let audio = spoken(&pauses);
        let mut calls = 0;
        let (mut pipeline, _) = pipeline(
            Box::new(move |samples| {
                calls += 1;
                let comma = if calls % 2 == 0 { "," } else { "" };
                hear(samples)
                    .into_iter()
                    .map(|w| Word {
                        text: format!("{}{comma}", w.text),
                        ..w
                    })
                    .collect()
            }),
            Box::new(|samples| {
                hear(samples)
                    .iter()
                    .map(|w| w.text.clone())
                    .collect::<Vec<_>>()
                    .join(" ")
            }),
        );
        let (text, updates) = dictate(&audio, &mut pipeline);
        assert_eq!(text.replace(',', ""), expected_words(30));
        assert!(updates.iter().all(|u| !u.stats.forced));
        assert!(updates.iter().filter(|u| !u.typed.is_empty()).count() >= 5);
        let waited = longest_wait(&updates);
        assert!(waited <= WAIT_BOUND_S, "a word waited {waited:.2} s");
    }

    #[test]
    fn slow_speech_is_typed_within_patience() {
        // #72: a word every 1.2 to 2 s, never a 2 s pause. Three words after a
        // word and four words per paste took up to nine seconds to come.
        let pauses = vec![0.9; 12];
        let audio = spoken(&pauses);
        let (mut pipeline, _) = hearing_pipeline();
        let (text, updates) = dictate(&audio, &mut pipeline);
        assert_eq!(text, expected_words(12));
        let waited = longest_wait(&updates);
        assert!(waited <= WAIT_BOUND_S, "a word waited {waited:.2} s");
    }

    #[test]
    fn a_word_is_committed_once_two_passes_agree_and_the_model_heard_past_it() {
        let hypothesis = vec![
            word("Je", 0.2, 0.5),
            word("vais", 0.6, 0.9),
            word("envoyer", 1.0, 1.5),
            word("le", 1.6, 1.8),
            word("rapport.", 1.9, 2.5),
            word("Pense", 3.0, 3.4),
            word("à", 3.5, 3.6),
            word("acheter", 3.7, 4.2),
        ];
        let (mut pipeline, calls) =
            pipeline(queue(vec![hypothesis.clone(), hypothesis]), no_plain());
        let mut streamer = Streamer::new();

        // 3.4 s: « Je » (ends 0.5 s) is heard 2.9 s past, under PATIENCE_S.
        streamer.push(&voiced(3.4));
        let first = pass_now(&mut streamer, &mut pipeline);
        assert_eq!((first.typed.as_str(), first.stats.stable), ("", 0));
        assert_eq!(
            first.provisional,
            "Je vais envoyer le rapport. Pense à acheter"
        );

        // 4.0 s heard: « rapport. » (ends 2.5 s) is 1.5 s behind with three
        // words after it; « Pense » (ends 3.4 s) only 0.6 s behind.
        streamer.push(&voiced(0.6));
        let second = pass_now(&mut streamer, &mut pipeline);
        assert_eq!(second.typed, "Je vais envoyer le rapport.");
        assert_eq!(second.provisional, "Pense à acheter");
        assert_eq!(second.stats.committed_words, 5);
        assert!((second.stats.audio_end_s - 2.5).abs() < 1e-3);
        // The passage lands at once: « Je » (ends 0.5 s) waited 3.5 s.
        assert!((second.stats.waited_s - 3.5).abs() < 0.05);
        assert_eq!(streamer.committed(), "Je vais envoyer le rapport.");

        // The boundary is just past « rapport. » (2.65 s), not the middle of
        // the gap: speech not heard yet may sit there. The window keeps the
        // 5 s before it, i.e. all of it: nothing is released yet.
        assert!((seconds_of(streamer.context) - 2.65).abs() < 1e-3);
        streamer.push(&voiced(0.6));
        pass_now(&mut streamer, &mut pipeline);
        let lengths = calls.lock().unwrap().timed.clone();
        assert_eq!(lengths[2], (4.6 * SAMPLE_RATE as f32) as usize);
    }

    #[test]
    fn a_provisional_period_waits_for_what_the_speaker_says_next() {
        // « faire. » at a thinking pause, then the speaker goes on.
        let paused = vec![
            word("on", 0.2, 0.4),
            word("pourrait", 0.5, 1.0),
            word("faire.", 1.1, 1.5),
        ];
        let went_on = vec![
            word("on", 0.2, 0.4),
            word("pourrait", 0.5, 1.0),
            word("faire", 1.1, 1.5),
            word("vraiment", 2.6, 3.0),
            word("de", 3.1, 3.2),
            word("l'affichage.", 3.3, 4.0),
        ];
        let said = "on pourrait faire vraiment de l'affichage.";
        let (mut pipeline, _) = pipeline(
            queue(vec![paused.clone(), paused, went_on]),
            Box::new(move |_| said.to_string()),
        );
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.6));
        pass_now(&mut streamer, &mut pipeline);
        // A 1.2 s pause: « faire. » agrees twice, but nothing follows it yet
        // and the speaker has not been silent 2 s.
        streamer.push(&silence(0.6));
        assert_eq!(pass_now(&mut streamer, &mut pipeline).typed, "");
        streamer.push(&silence(0.6));
        streamer.push(&voiced(1.8));
        let update = pass_now(&mut streamer, &mut pipeline);
        // « faire » lost its period: it no longer agrees, but it was heard
        // 3.1 s ago, past PATIENCE_S: typed as this pass heard it, without the
        // period. « vraiment » onwards waits.
        assert_eq!(update.typed, "on pourrait faire");
        assert_eq!(update.provisional, "vraiment de l'affichage.");
        let finish = streamer.finish(&mut pipeline).unwrap();
        assert_eq!(
            format!("{}{}", update.typed, finish.typed),
            "on pourrait faire vraiment de l'affichage."
        );
    }

    #[test]
    fn speech_heard_only_after_a_commit_in_the_gap_is_still_typed() {
        // The first passes hear « sans ça. » then « été … » and skip the
        // hesitation between; a later pass hears it. It must not fall into
        // the context.
        let early = vec![
            word("sans", 0.2, 0.6),
            word("ça.", 0.7, 1.0),
            word("été", 3.0, 3.3),
            word("beaucoup", 3.4, 3.8),
            word("plus", 3.9, 4.1),
            word("compliqué.", 4.2, 4.8),
        ];
        let late = vec![
            word("sans", 0.2, 0.6),
            word("ça.", 0.7, 1.0),
            word("Euh...", 1.6, 2.0),
            word("ça", 2.2, 2.4),
            word("aurait", 2.5, 2.9),
            word("été", 3.0, 3.3),
            word("beaucoup", 3.4, 3.8),
            word("plus", 3.9, 4.1),
            word("compliqué.", 4.2, 4.8),
        ];
        let (mut pipeline, _) = pipeline(queue(vec![early.clone(), early, late]), no_plain());
        let mut streamer = Streamer::new();
        streamer.push(&voiced(5.0));
        // « sans » was heard 4.4 s ago, past PATIENCE_S: this pass is trusted
        // alone, but not across the 2 s gap after « ça. ».
        assert_eq!(pass_now(&mut streamer, &mut pipeline).typed, "sans ça.");
        streamer.push(&voiced(0.6));
        pass_now(&mut streamer, &mut pipeline);
        let committed = streamer.committed().to_string();
        let finish = streamer.finish(&mut pipeline).unwrap();
        assert_eq!(
            format!("{committed}{}", finish.typed),
            "sans ça. Euh... ça aurait été beaucoup plus compliqué."
        );
    }

    #[test]
    fn the_words_heard_in_the_context_are_never_typed_twice() {
        let (mut pipeline, _) = hearing_pipeline();
        // Four words, a pause, four more: later windows start in the context
        // of the first words.
        let audio = spoken(&[0.15, 0.15, 0.15, 1.2, 0.15, 0.15, 0.15, 2.5]);
        let (text, updates) = dictate(&audio, &mut pipeline);
        assert_eq!(text, expected_words(8));
        assert!(updates.iter().filter(|u| !u.typed.is_empty()).count() >= 2);
    }

    #[test]
    fn the_last_word_is_committed_after_two_seconds_of_silence() {
        let hypothesis = vec![word("Bonjour", 0.2, 1.1)];
        let (mut pipeline, calls) = pipeline(queue(vec![hypothesis]), no_plain());
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.2));
        pass_now(&mut streamer, &mut pipeline);
        let mut typed = String::new();
        let mut silent_s = 0.0;
        while typed.is_empty() {
            streamer.push(&silence(0.6));
            silent_s += 0.6;
            typed = pass_now(&mut streamer, &mut pipeline).typed;
            assert!(silent_s < 5.0, "never committed");
        }
        assert!(1.2 + silent_s - 1.1 >= COMMIT_PAUSE_S);
        assert!(1.2 + silent_s - 0.6 - 1.1 < COMMIT_PAUSE_S);
        assert_eq!(typed, "Bonjour");

        // Silence after everything is committed makes no engine call.
        let before = calls.lock().unwrap().timed.len();
        for _ in 0..100 {
            streamer.push(&silence(0.1));
            assert!(!streamer.is_pass_due());
        }
        assert_eq!(calls.lock().unwrap().timed.len(), before);
    }

    /// Two passes over `words` (window of 4.6 s), then the stop: the text typed
    /// by the passes, and the whole typed text.
    fn live_numbers(words: &[Word]) -> (String, String, Pipeline) {
        let hypothesis = words.to_vec();
        let block: String = words
            .iter()
            .map(|w| w.text.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        let (mut pipeline, _) = pipeline(
            queue(vec![hypothesis.clone(), hypothesis]),
            Box::new(move |_| block.clone()),
        );
        let mut streamer = Streamer::new();
        streamer.push(&voiced(4.0));
        let first = pass_now(&mut streamer, &mut pipeline);
        streamer.push(&voiced(0.6));
        let second = pass_now(&mut streamer, &mut pipeline);
        let finish = streamer.finish(&mut pipeline).unwrap();
        let by_passes = format!("{}{}", first.typed, second.typed);
        let whole = format!("{by_passes}{}", finish.typed);
        (by_passes, whole, pipeline)
    }

    #[test]
    fn a_number_cut_between_two_passages_is_typed_whole_and_equals_the_block() {
        let cases = [
            // « quatre-vingt » | « -dix ».
            (
                vec![
                    word("Ajoute", 0.2, 0.5),
                    word("moi", 0.6, 0.9),
                    word("les", 1.0, 1.2),
                    word("quatre-vingt", 1.3, 1.8),
                    word("-dix", 1.9, 3.4),
                    word("tests", 3.5, 3.7),
                    word("sous", 3.8, 4.0),
                    word("demain", 4.1, 4.3),
                ],
                "Ajoute moi les",
                "Ajoute moi les 90 tests sous demain",
            ),
            // « quatorze heures » | « trente ».
            (
                vec![
                    word("Rappelle", 0.2, 0.5),
                    word("moi", 0.6, 0.9),
                    word("à", 1.0, 1.2),
                    word("quatorze", 1.3, 1.6),
                    word("heures", 1.7, 2.1),
                    word("trente", 2.2, 3.6),
                    word("chez", 3.7, 3.9),
                    word("Paul", 4.0, 4.2),
                ],
                "Rappelle moi à",
                "Rappelle moi à 14 h 30 chez Paul",
            ),
        ];
        for (words, by_passes, whole) in cases {
            let (typed_by_passes, typed, mut pipeline) = live_numbers(&words);
            assert_eq!(typed_by_passes, by_passes);
            assert_eq!(typed, whole);
            // The same words in one block (V2's block and hold dictation).
            let block = pipeline.transcribe(&voiced(4.6)).unwrap().text;
            assert_eq!(typed, block);
        }
    }

    /// Answers like [`Fake`] until `ok_calls` timed calls are made, then fails.
    struct Failing {
        timed: Timed,
        ok_calls: usize,
    }

    impl Transcriber for Failing {
        fn name(&self) -> &'static str {
            "failing"
        }
        fn transcribe(&mut self, _: &[f32]) -> Result<String, Error> {
            Err(Error::ModelMissing("gone".into()))
        }
        fn transcribe_timed(&mut self, samples: &[f32]) -> Result<Option<Vec<Word>>, Error> {
            if self.ok_calls == 0 {
                return Err(Error::ModelMissing("gone".into()));
            }
            self.ok_calls -= 1;
            Ok(Some((self.timed)(samples)))
        }
    }

    /// Two passes that commit « Rappelle moi à quatorze heures », the number
    /// held back; returns the streamer and the pipeline whose engine then fails.
    fn streamer_holding_a_number() -> (Streamer, Pipeline, String) {
        let hypothesis = vec![
            word("Rappelle", 0.2, 0.5),
            word("moi", 0.6, 0.9),
            word("à", 1.0, 1.2),
            word("quatorze", 1.3, 1.6),
            word("heures", 1.7, 2.1),
            word("trente", 2.2, 3.6),
            word("chez", 3.7, 3.9),
            word("Paul", 4.0, 4.2),
        ];
        let engine = Failing {
            timed: queue(vec![hypothesis.clone(), hypothesis]),
            ok_calls: 2,
        };
        let mut pipeline = Pipeline::new(Box::new(engine), None, Strategy::Padded);
        let mut streamer = Streamer::new();
        streamer.push(&voiced(4.0));
        let first = pass_now(&mut streamer, &mut pipeline);
        streamer.push(&voiced(0.6));
        let second = pass_now(&mut streamer, &mut pipeline);
        let typed = format!("{}{}", first.typed, second.typed);
        (streamer, pipeline, typed)
    }

    #[test]
    fn a_number_held_back_is_typed_when_the_engine_fails_at_the_stop() {
        let (streamer, mut pipeline, typed) = streamer_holding_a_number();
        assert_eq!(typed, "Rappelle moi à");
        let finish = streamer.finish(&mut pipeline).unwrap();
        assert_eq!(finish.typed, " 14 heures");
        assert!(
            finish.lost.is_some(),
            "the audio the engine failed on is kept"
        );
    }

    #[test]
    fn a_stop_that_fails_with_nothing_held_still_reports_the_error() {
        let engine = Failing {
            timed: queue(vec![]),
            ok_calls: 0,
        };
        let mut pipeline = Pipeline::new(Box::new(engine), None, Strategy::Padded);
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.0));
        assert!(streamer.finish(&mut pipeline).is_err());
    }

    #[test]
    fn a_number_held_back_is_typed_when_the_stop_has_nothing_to_hear() {
        let (streamer, _, _) = streamer_holding_a_number();
        assert_eq!(streamer.flush(), " 14 heures");
    }

    #[test]
    fn a_number_a_guard_rejected_is_never_retyped_when_it_grows() {
        let mut streamer = Streamer::new();
        let first = streamer.commit_text("the cent", &[], false, false);
        let second = streamer.commit_text("vingt ans", &[], false, false);
        let rest = streamer.commit_text("", &[], false, true);
        assert_eq!(first, "the");
        assert_eq!(
            format!("{first}{second}{rest}"),
            itn::normalize("the cent vingt ans")
        );
    }

    #[test]
    fn a_commit_of_nothing_counts_no_words() {
        let mut streamer = Streamer::new();
        streamer.commit_text("à quatorze heures", &[], false, false);
        assert_eq!(streamer.last_words, 3);
        streamer.commit_text("", &[], false, false);
        assert_eq!(streamer.last_words, 0);
    }

    #[test]
    fn the_caption_shows_the_committed_text_in_digits() {
        let mut streamer = Streamer::new();
        streamer.commit_text("à quatorze heures trente", &[], false, false);
        assert_eq!(streamer.committed(), "à 14 h 30");
        assert_eq!(streamer.commit_text("", &[], false, true), " 14 h 30");
    }

    #[test]
    fn heard_without_context_after_a_text_left_open_continues_it() {
        let mut streamer = Streamer::new();
        assert_eq!(
            streamer.commit_text("Il y a des tickets", &[], true, true),
            "Il y a des tickets"
        );
        assert_eq!(
            streamer.commit_text("Qui se baladent.", &[], false, true),
            " qui se baladent."
        );
        assert_eq!(
            streamer.commit_text("Ensuite", &[], false, true),
            " Ensuite"
        );
        // In context the model's capitals stand (a proper noun mid-sentence).
        assert_eq!(streamer.commit_text("Pierre", &[], true, true), " Pierre");
        assert_eq!(
            streamer.commit_text("API demain", &[], false, true),
            " API demain"
        );
        // After a typed period a capital follows, whoever heard the period;
        // after an ellipsis the model's case stands.
        assert_eq!(
            streamer.commit_text("donc bon.", &[], true, true),
            " donc bon."
        );
        assert_eq!(
            streamer.commit_text("pensez-y", &[], true, true),
            " Pensez-y"
        );
        assert_eq!(
            streamer.commit_text("sera de...", &[], true, true),
            " sera de..."
        );
        assert_eq!(streamer.commit_text("pouvoir", &[], true, true), " pouvoir");
    }

    #[test]
    fn an_overflowing_window_is_committed_whole_through_the_pipeline() {
        // An engine that never hears a timed word: only the overflow commits.
        let (mut pipeline, calls) = pipeline(
            Box::new(|_| Vec::new()),
            Box::new(|_| "tout un bloc".to_string()),
        );
        let mut streamer = Streamer::new();
        let mut typed = String::new();
        for _ in 0..42 {
            streamer.push(&voiced(0.5));
            if streamer.is_pass_due() {
                let update = streamer.pass(&mut pipeline).unwrap();
                if !update.typed.is_empty() {
                    assert!(update.stats.forced);
                    typed.push_str(&update.typed);
                }
            }
        }
        assert_eq!(typed, "tout un bloc");
        let calls = calls.lock().unwrap();
        assert!(calls
            .timed
            .iter()
            .chain(&calls.plain)
            .all(|&n| n <= MAX_CALL));
    }

    #[test]
    fn leading_silence_costs_no_engine_call() {
        let (mut pipeline, calls) = pipeline(queue(vec![]), no_plain());
        let mut streamer = Streamer::new();
        for _ in 0..30 {
            streamer.push(&silence(0.5));
            assert!(!streamer.is_pass_due());
        }
        let finish = streamer.finish(&mut pipeline).unwrap();
        assert_eq!(finish, Finish::default());
        assert!(calls.lock().unwrap().timed.is_empty());
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
        let calls = calls.lock().unwrap();
        // The pause and the context were released with no engine call: the
        // timed pass heard the lead-in and the new speech only.
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
    fn the_stop_hears_the_open_audio_in_its_context() {
        let (mut pipeline, calls) = hearing_pipeline();
        let mut streamer = Streamer::new();
        // Words committed while spoken, then two still open at the stop.
        let audio = spoken(&[0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.3]);
        for block in audio.chunks(800) {
            streamer.push(block);
            if streamer.is_pass_due() {
                streamer.pass(&mut pipeline).unwrap();
            }
        }
        let committed = streamer.committed().to_string();
        assert!(!committed.is_empty() && streamer.context > 0);
        let plain_before = calls.lock().unwrap().plain.len();
        let finish = streamer.finish(&mut pipeline).unwrap();
        assert_eq!(format!("{committed}{}", finish.typed), expected_words(7));
        assert_eq!(finish.engine, Some("fake"));
        assert_eq!(finish.lost, None);
        // Heard in context: no call of the full pipeline.
        assert_eq!(calls.lock().unwrap().plain.len(), plain_before);
    }

    #[test]
    fn a_stop_that_hears_no_word_in_speech_reports_the_audio_lost() {
        let (mut pipeline, _) = pipeline(Box::new(|_| Vec::new()), no_plain());
        let mut streamer = Streamer::new();
        streamer.push(&voiced(1.5));
        let finish = streamer.finish(&mut pipeline).unwrap();
        assert_eq!(finish.typed, "");
        assert_eq!(finish.engine, None);
        assert_eq!(finish.lost.map(|clip| clip.len()), Some(24_000));
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
        assert_eq!(streamer.finish(&mut pipeline).unwrap().typed, "mot");
    }

    #[test]
    fn the_context_starts_in_a_gap() {
        let words = [
            word("a", 0.0, 1.0),
            word("b", 1.4, 2.0),
            word("c", 2.2, 3.0),
        ];
        // In the gap a–b: as asked.
        assert_eq!(context_start(&words, 1.2), 1.2);
        // Inside « b »: the gap before « c ».
        assert_eq!(context_start(&words, 1.7), 2.1);
        // Before the window: keep it all.
        assert_eq!(context_start(&words, -0.5), 0.0);
        assert_eq!(first_after(&words, 1.6), 1);
        assert_eq!(first_after(&words, 5.0), 3);
    }
}

//! « Type while speaking »: three ways to turn the same audio into text,
//! compared by `banc --streaming`.
//!
//! - **block**: [`Pipeline::transcribe`] on the whole clip (the quality bar);
//! - **pieces**: the previous design, [`LiveSplitter`] cutting at pauses while
//!   the microphone runs, each piece transcribed alone, [`PieceJoiner`] joining
//!   them (the baseline);
//! - **rolling**: [`Streamer`], the open window re-transcribed as the audio
//!   comes, simulated at real-time pace ([`simulate`]): 50 ms blocks, one
//!   worker, a pass starts only when the worker is free, its text is typed
//!   when it ends.
//!
//! Clips, in two groups: the references (two sentences with 1 s and with 0.2 s
//! between them, the long clip with 1 s of silence inserted in its longest
//! gap, the long clip as is) and the user's labelled speech clips of 8 s or
//! more (`~/.whispy/bench`). The labelled clips are the user's voice: only ids,
//! lengths and numbers are printed, never a text.
//!
//! Per clip and per group: WER against the expected text, extra sentence ends
//! against the block text; for rolling also the commit delay (typing time
//! minus the committed audio's end), the stop latency (stop to last text), the
//! pass cost (pass time over audio time) and the forced commits.
//!
//! Criteria (exit 1 when one fails), per group: 1. rolling WER ≤ block WER + 1
//! point; 2. rolling WER ≤ pieces WER; 3. rolling has fewer extra sentence ends
//! than pieces (none if pieces has none). Overall: 4. commit delay p95 ≤ 4 s,
//! stop latency p95 ≤ 1 s, mean pass cost ≤ 0.5; 5. in a fresh process, a 180 s
//! dictation through the rolling streamer peaks ≤ 1.5 GB.

use std::process::ExitCode;
use std::time::Instant;

use whispy_core::audio::{self, SAMPLE_RATE};
use whispy_core::join::PieceJoiner;
use whispy_core::split::{LiveSplitter, Piece};
use whispy_core::stream::{Streamer, Update};
use whispy_core::vad;
use whispy_core::{Error, Pipeline};

use crate::labelled::{self, Kind};
use crate::{corpus, memory, wer};

const FIRST: (&str, &str) = (
    "fr-sentence-rapport.wav",
    "je vais envoyer le rapport à l'équipe demain matin avant la réunion",
);
const SECOND: (&str, &str) = (
    "fr-sentence-courses.wav",
    "pense à acheter du pain et des tomates en rentrant ce soir",
);
const RUN_ON: (&str, &str) = (
    "fr-long-projet.wav",
    "nous avons terminé la première version du projet la semaine dernière, mais il reste plusieurs problèmes à corriger avant de la présenter aux utilisateurs, notamment la vitesse et la fiabilité de la transcription",
);
const PAUSE_S: f32 = 1.0;
const BACK_TO_BACK_S: f32 = 0.2;
const THINKING_PAUSE_S: f32 = 1.0;
/// 50 ms at 16 kHz: the beat at which the app drains the microphone.
const BLOCK: usize = 800;
const DICTATION_SECONDS: f32 = 180.0;
const MEMORY_TARGET_BYTES: u64 = 1_500_000_000;
const LABELLED_MIN_S: f32 = 8.0;
const WER_MARGIN: f64 = 0.01;
/// 3 s at first; raised to 4 s (2026-11-24) once a word needed three words
/// heard after it and passages of four words per paste: those cost about a
/// second at p95 (median 1.9 s) and removed every extra period the bench saw.
/// The pill shows the words live meanwhile.
const COMMIT_DELAY_P95_S: f64 = 4.0;
/// The oldest word of a passage, from its audio end to its typing (#72):
/// the wait the speaker sees.
/// Measured 2026-11-28: p95 5.3 s, max 9.9 s before `PATIENCE_S`; p95 3.8 s,
/// max 5.0 s with it.
const WAIT_P95_S: f64 = 4.5;
const WAIT_MAX_S: f64 = 6.0;
const STOP_LATENCY_P95_S: f64 = 1.0;
const PASS_COST_MAX: f64 = 0.5;

// --- pure parts -------------------------------------------------------------

/// `.`, `?`, `!` and `…` in `text`.
fn sentence_ends(text: &str) -> usize {
    text.chars()
        .filter(|c| matches!(c, '.' | '?' | '!' | '\u{2026}'))
        .count()
}

/// Sentence ends `text` has beyond the one-block text's.
fn extra_sentence_ends(text: &str, block: &str) -> usize {
    sentence_ends(text).saturating_sub(sentence_ends(block))
}

/// Nearest-rank percentile (`p` in 0..=100) of `values`; `None` when empty.
fn percentile(values: &[f64], p: f64) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.total_cmp(b));
    let rank = ((p / 100.0) * sorted.len() as f64).ceil() as usize;
    Some(sorted[rank.clamp(1, sorted.len()) - 1])
}

/// The frame index at the middle of the longest unvoiced run that starts after
/// frame 0 (leading silence is not a thinking pause) within `voiced[..limit]`.
fn longest_gap_middle(voiced: &[bool], limit: usize) -> Option<usize> {
    let limit = limit.min(voiced.len());
    let mut best: Option<(usize, usize)> = None;
    // Runs of `false`, ignoring the one that starts at frame 0.
    let mut start = None;
    for (i, &is_voiced) in voiced[..limit].iter().enumerate() {
        match (is_voiced, start) {
            (false, None) => start = Some(i),
            (true, Some(s)) => {
                if s > 0 && best.is_none_or(|(_, len)| i - s > len) {
                    best = Some((s, i - s));
                }
                start = None;
            }
            _ => {}
        }
    }
    best.map(|(s, len)| s + len / 2)
}

/// `samples` with `pause_s` of silence inserted in the middle of its longest
/// unvoiced run within the first half; `None` when it has no such run.
fn with_thinking_pause(samples: &[f32], pause_s: f32) -> Option<Vec<f32>> {
    let voiced = vad::voiced_frames(samples);
    let frame = (vad::frame_seconds() * SAMPLE_RATE as f32).round() as usize;
    let middle = longest_gap_middle(&voiced, voiced.len() / 2)? * frame;
    let silence = vec![0.0; (pause_s * SAMPLE_RATE as f32) as usize];
    Some([&samples[..middle], &silence, &samples[middle..]].concat())
}

// --- the rolling simulation -------------------------------------------------

/// What [`simulate`] drives: the streamer and its engine, with each call's
/// wall time (a fake in the tests).
trait Worker {
    fn push(&mut self, samples: &[f32]);
    fn is_pass_due(&self) -> bool;
    fn pass(&mut self) -> Result<(Update, f64), Error>;
    /// The stop: the text to append and the time it took.
    fn finish(self) -> Result<(String, f64), Error>;
}

struct Real<'a> {
    streamer: Streamer,
    pipeline: &'a mut Pipeline,
}

impl Worker for Real<'_> {
    fn push(&mut self, samples: &[f32]) {
        self.streamer.push(samples);
    }
    fn is_pass_due(&self) -> bool {
        self.streamer.is_pass_due()
    }
    fn pass(&mut self) -> Result<(Update, f64), Error> {
        let started = Instant::now();
        let update = self.streamer.pass(self.pipeline)?;
        Ok((update, started.elapsed().as_secs_f64()))
    }
    fn finish(self) -> Result<(String, f64), Error> {
        let started = Instant::now();
        let text = self.streamer.finish(self.pipeline)?.typed;
        Ok((text, started.elapsed().as_secs_f64()))
    }
}

#[derive(Debug, Default, PartialEq)]
struct Rolling {
    text: String,
    /// Each commit's text, then the stop's, in typing order (for a local
    /// `WHISPY_BANC_SHOW_LOST_TEXT=1` run only: never printed otherwise).
    typed: Vec<String>,
    /// Per commit: typing time minus the committed audio's end, seconds.
    commit_delays: Vec<f64>,
    /// The delays of the commits cut mid-sentence (also in `commit_delays`).
    forced_delays: Vec<f64>,
    /// Per pass that typed: how long its oldest word waited (its audio end to
    /// the typing), seconds. A passage lands at once: this is the wait the
    /// speaker sees, where `commit_delays` dates the passage's last word.
    waits: Vec<f64>,
    /// The open window's length, seconds, at each commit.
    commit_windows: Vec<f64>,
    stop_latency: f64,
    pass_times: Vec<f64>,
    forced: usize,
    audio_s: f64,
}

/// Feeds `samples` in 50 ms blocks at real-time pace to one worker: a pass
/// starts when the audio clock `t` has reached `busy_until` and one is due,
/// and its text is typed at `t + d`. The stop runs `finish` once the worker is
/// free.
fn simulate<W: Worker>(mut worker: W, samples: &[f32]) -> Result<Rolling, Error> {
    let rate = SAMPLE_RATE as f64;
    let mut run = Rolling::default();
    let mut t = 0.0;
    let mut busy_until = 0.0;
    for block in samples.chunks(BLOCK) {
        worker.push(block);
        t += block.len() as f64 / rate;
        if t >= busy_until && worker.is_pass_due() {
            let (update, d) = worker.pass()?;
            busy_until = t + d;
            run.pass_times.push(d);
            run.forced += usize::from(update.stats.forced);
            if !update.typed.is_empty() {
                run.text.push_str(&update.typed);
                run.typed.push(update.typed.clone());
                let delay = t + d - update.stats.audio_end_s as f64;
                run.commit_delays.push(delay);
                run.commit_windows.push(update.stats.window_s as f64);
                run.waits.push(update.stats.waited_s as f64);
                if update.stats.forced {
                    run.forced_delays.push(delay);
                }
            }
        }
    }
    let (text, d_finish) = worker.finish()?;
    run.text.push_str(&text);
    run.typed.push(text);
    run.stop_latency = f64::max(t, busy_until) - t + d_finish;
    run.audio_s = t;
    Ok(run)
}

// --- the three ways, per clip -----------------------------------------------

fn pieces_text(pipeline: &mut Pipeline, samples: &[f32]) -> Result<String, Error> {
    let mut joiner = PieceJoiner::default();
    let mut typed = String::new();
    for piece in split_as_recorded(samples) {
        let text = pipeline.transcribe(&piece.samples)?.text;
        if !text.trim().is_empty() {
            typed.push_str(&joiner.next(&text, piece.is_cut_mid_speech));
        }
    }
    typed.push_str(joiner.end());
    Ok(typed)
}

/// The pieces the app would queue: closed while recording, then the rest at
/// the stop (which always ends a sentence).
fn split_as_recorded(samples: &[f32]) -> Vec<Piece> {
    let mut splitter = LiveSplitter::new();
    let mut pieces = Vec::new();
    for block in samples.chunks(BLOCK) {
        pieces.extend(splitter.push(block));
    }
    pieces.push(Piece {
        samples: splitter.finish(),
        is_cut_mid_speech: false,
    });
    pieces
}

#[derive(Clone, Copy)]
enum Normalizer {
    Bench,
    V1,
}

impl Normalizer {
    fn words(self, text: &str) -> Vec<String> {
        match self {
            Normalizer::Bench => wer::normalized_words(text),
            Normalizer::V1 => labelled::v1_words(text),
        }
    }
}

struct Clip {
    id: String,
    expected: String,
    samples: Vec<f32>,
    normalizer: Normalizer,
}

/// One way's text on one clip, scored.
struct Way {
    errors: usize,
    extra_ends: usize,
}

struct ClipResult {
    id: String,
    audio_s: f64,
    ref_words: usize,
    block: Way,
    pieces: Way,
    rolling: Way,
    run: Rolling,
}

fn score_way(clip: &Clip, text: &str, block: &str) -> Way {
    let expected = clip.normalizer.words(&clip.expected);
    Way {
        errors: wer::word_edits(&expected, &clip.normalizer.words(text)),
        extra_ends: extra_sentence_ends(text, block),
    }
}

fn run_clip(pipeline: &mut Pipeline, clip: &Clip) -> Result<ClipResult, String> {
    let to_string = |error: Error| error.to_string();
    let block = pipeline.transcribe(&clip.samples).map_err(to_string)?.text;
    let pieces = pieces_text(pipeline, &clip.samples).map_err(to_string)?;
    let run = simulate(
        Real {
            streamer: Streamer::new(),
            pipeline,
        },
        &clip.samples,
    )
    .map_err(to_string)?;
    // The user's voice: texts only on request, in a local run (as `banc`'s lost clips).
    if std::env::var_os("WHISPY_BANC_SHOW_LOST_TEXT").is_some() {
        println!("  block:   {block}");
        println!("  pieces:  {pieces}");
        println!("  rolling: {}", run.typed.join(" ‖"));
    }
    Ok(ClipResult {
        id: clip.id.clone(),
        audio_s: audio::seconds(&clip.samples) as f64,
        ref_words: clip.normalizer.words(&clip.expected).len(),
        block: score_way(clip, &block, &block),
        pieces: score_way(clip, &pieces, &block),
        rolling: score_way(clip, &run.text, &block),
        run,
    })
}

// --- the clips --------------------------------------------------------------

fn references() -> Result<Vec<Clip>, String> {
    let dir = corpus::bench_dir().join("reference");
    let read = |file: &str| audio::read_wav(&dir.join(file)).map_err(|error| error.to_string());
    let silence = |seconds: f32| vec![0.0; (seconds * SAMPLE_RATE as f32) as usize];
    let (first, second, run_on) = (read(FIRST.0)?, read(SECOND.0)?, read(RUN_ON.0)?);
    let two = format!("{} {}", FIRST.1, SECOND.1);
    let clip = |id: &str, expected: &str, samples: Vec<f32>| Clip {
        id: id.to_string(),
        expected: expected.to_string(),
        samples,
        normalizer: Normalizer::Bench,
    };
    let mut clips = vec![
        clip(
            "two-sentences+1.0s",
            &two,
            [first.clone(), silence(PAUSE_S), second.clone()].concat(),
        ),
        clip(
            "two-sentences+0.2s",
            &two,
            [first, silence(BACK_TO_BACK_S), second].concat(),
        ),
    ];
    match with_thinking_pause(&run_on, THINKING_PAUSE_S) {
        Some(samples) => clips.push(clip("thinking-pause", RUN_ON.1, samples)),
        None => println!(
            "no unvoiced run in the first half of {}: thinking pause skipped",
            RUN_ON.0
        ),
    }
    clips.push(clip("run-on", RUN_ON.1, run_on));
    Ok(clips)
}

fn labelled_speech() -> Vec<Clip> {
    let clips = match labelled::bench_set() {
        Ok((clips, _)) => clips,
        Err(message) => {
            println!("labelled clips unavailable ({message}): references only");
            return Vec::new();
        }
    };
    let mut kept = Vec::new();
    for clip in clips {
        if clip.label.kind == Kind::Noise || clip.label.reference.trim().is_empty() {
            continue;
        }
        let Ok(samples) = audio::read_wav(&clip.wav) else {
            continue;
        };
        if audio::seconds(&samples) >= LABELLED_MIN_S {
            kept.push(Clip {
                id: clip.id,
                expected: clip.label.reference,
                samples,
                normalizer: Normalizer::V1,
            });
        }
    }
    if kept.is_empty() {
        println!("no labelled speech clip of {LABELLED_MIN_S:.0} s or more on this machine: references only");
    }
    kept
}

// --- the report -------------------------------------------------------------

fn rate(errors: usize, words: usize) -> f64 {
    if words == 0 {
        0.0
    } else {
        errors as f64 / words as f64
    }
}

fn pct(value: f64) -> String {
    format!("{:5.1}", value * 100.0)
}

fn opt(value: Option<f64>) -> String {
    value.map_or("-".to_string(), |v| format!("{v:.2}"))
}

struct Group {
    name: &'static str,
    results: Vec<ClipResult>,
}

impl Group {
    fn wer(&self, way: impl Fn(&ClipResult) -> &Way) -> f64 {
        let errors = self.results.iter().map(|r| way(r).errors).sum();
        rate(errors, self.results.iter().map(|r| r.ref_words).sum())
    }

    fn extra_ends(&self, way: impl Fn(&ClipResult) -> &Way) -> usize {
        self.results.iter().map(|r| way(r).extra_ends).sum()
    }

    fn print(&self) {
        println!("\n== {} ({} clips) ==", self.name, self.results.len());
        println!(
            "{:<28} {:>6} | WER % block pieces rolling | ends+ pieces rolling | delay p50/p95 | wait p95/max | stop s | cost  | forced",
            "clip", "audio"
        );
        for r in &self.results {
            println!(
                "{:<28} {:>5.1}s |       {}  {}  {} |        {:>6} {:>7} | {:>5}/{:<5}   | {:>5}/{:<5}  | {:>6.2} | {:>5.2} | {:>6}",
                r.id,
                r.audio_s,
                pct(rate(r.block.errors, r.ref_words)),
                pct(rate(r.pieces.errors, r.ref_words)),
                pct(rate(r.rolling.errors, r.ref_words)),
                r.pieces.extra_ends,
                r.rolling.extra_ends,
                opt(percentile(&r.run.commit_delays, 50.0)),
                opt(percentile(&r.run.commit_delays, 95.0)),
                opt(percentile(&r.run.waits, 95.0)),
                opt(percentile(&r.run.waits, 100.0)),
                r.run.stop_latency,
                pass_cost_of(&[&r.run]),
                r.run.forced
            );
        }
        let runs: Vec<&Rolling> = self.results.iter().map(|r| &r.run).collect();
        println!(
            "{:<28} {:>6} |       {}  {}  {} |        {:>6} {:>7} | {:>5}/{:<5}   | {:>5}/{:<5}  | {:>6.2} | {:>5.2} | {:>6}",
            "GROUP",
            "",
            pct(self.wer(|r| &r.block)),
            pct(self.wer(|r| &r.pieces)),
            pct(self.wer(|r| &r.rolling)),
            self.extra_ends(|r| &r.pieces),
            self.extra_ends(|r| &r.rolling),
            opt(percentile(&all(&runs, |r| &r.commit_delays), 50.0)),
            opt(percentile(&all(&runs, |r| &r.commit_delays), 95.0)),
            opt(percentile(&all(&runs, |r| &r.waits), 95.0)),
            opt(percentile(&all(&runs, |r| &r.waits), 100.0)),
            percentile(&runs.iter().map(|r| r.stop_latency).collect::<Vec<_>>(), 95.0)
                .unwrap_or(0.0),
            pass_cost_of(&runs),
            runs.iter().map(|r| r.forced).sum::<usize>()
        );
    }
}

fn all(runs: &[&Rolling], field: impl Fn(&Rolling) -> &Vec<f64>) -> Vec<f64> {
    runs.iter().flat_map(|r| field(r).iter().copied()).collect()
}

fn pass_cost_of(runs: &[&Rolling]) -> f64 {
    let pass: f64 = runs.iter().flat_map(|r| &r.pass_times).sum();
    let audio: f64 = runs.iter().map(|r| r.audio_s).sum();
    if audio == 0.0 {
        0.0
    } else {
        pass / audio
    }
}

fn mark(is_met: bool) -> &'static str {
    if is_met {
        "✓"
    } else {
        "✗"
    }
}

/// Group criteria 1–3, as (label, met) lines.
fn group_criteria(group: &Group) -> Vec<(String, bool)> {
    let (block, pieces, rolling) = (
        group.wer(|r| &r.block),
        group.wer(|r| &r.pieces),
        group.wer(|r| &r.rolling),
    );
    let (pieces_ends, rolling_ends) = (
        group.extra_ends(|r| &r.pieces),
        group.extra_ends(|r| &r.rolling),
    );
    vec![
        (
            format!(
                "1 [{}] rolling WER {:.1} % ≤ block {:.1} % + 1 point",
                group.name,
                rolling * 100.0,
                block * 100.0
            ),
            rolling <= block + WER_MARGIN + 1e-9,
        ),
        (
            format!(
                "2 [{}] rolling WER {:.1} % ≤ pieces {:.1} %",
                group.name,
                rolling * 100.0,
                pieces * 100.0
            ),
            rolling <= pieces + 1e-9,
        ),
        (
            format!(
                "3 [{}] rolling extra sentence ends {rolling_ends} < pieces {pieces_ends} (0 if pieces has 0)",
                group.name
            ),
            if pieces_ends == 0 {
                rolling_ends == 0
            } else {
                rolling_ends < pieces_ends
            },
        ),
    ]
}

pub fn run() -> Result<ExitCode, String> {
    let mut pipeline = Pipeline::load_default().map_err(|error| error.to_string())?;
    let mut groups = Vec::new();
    for (name, clips) in [
        ("references", references()?),
        ("labelled", labelled_speech()),
    ] {
        if clips.is_empty() {
            continue;
        }
        let mut results = Vec::new();
        for clip in &clips {
            println!(
                "running {} ({:.1} s)",
                clip.id,
                audio::seconds(&clip.samples)
            );
            results.push(run_clip(&mut pipeline, clip)?);
        }
        groups.push(Group { name, results });
    }
    for group in &groups {
        group.print();
    }

    let runs: Vec<&Rolling> = groups
        .iter()
        .flat_map(|g| g.results.iter().map(|r| &r.run))
        .collect();
    let delays = all(&runs, |r| &r.commit_delays);
    let waits = all(&runs, |r| &r.waits);
    let stops: Vec<f64> = runs.iter().map(|r| r.stop_latency).collect();
    let passes = all(&runs, |r| &r.pass_times);
    println!(
        "\nrolling overall: commit delay p50 {} / p95 {} s over {} commits; stop latency p50 {} / p95 {} s; \
         mean pass cost {:.2}; pass time p50 {} / p95 {} s over {} passes; {} forced commits",
        opt(percentile(&delays, 50.0)),
        opt(percentile(&delays, 95.0)),
        delays.len(),
        opt(percentile(&stops, 50.0)),
        opt(percentile(&stops, 95.0)),
        pass_cost_of(&runs),
        opt(percentile(&passes, 50.0)),
        opt(percentile(&passes, 95.0)),
        passes.len(),
        runs.iter().map(|r| r.forced).sum::<usize>()
    );

    let forced = all(&runs, |r| &r.forced_delays);
    let unforced: Vec<f64> = runs
        .iter()
        .flat_map(|r| r.commit_delays.iter().copied())
        .filter(|d| !forced.contains(d))
        .collect();
    println!(
        "commit delay split: sentence commits p50 {} / p95 {} s over {}; forced commits p50 {} / p95 {} s over {}; \
         window at commit p50 {} / p95 {} s; {} of {} commits over 3 s",
        opt(percentile(&unforced, 50.0)),
        opt(percentile(&unforced, 95.0)),
        unforced.len(),
        opt(percentile(&forced, 50.0)),
        opt(percentile(&forced, 95.0)),
        forced.len(),
        opt(percentile(&all(&runs, |r| &r.commit_windows), 50.0)),
        opt(percentile(&all(&runs, |r| &r.commit_windows), 95.0)),
        delays.iter().filter(|&&d| d > COMMIT_DELAY_P95_S).count(),
        delays.len()
    );

    println!(
        "first-word wait: p50 {} / p95 {} / max {} s over {} passages; {} over {WAIT_P95_S} s",
        opt(percentile(&waits, 50.0)),
        opt(percentile(&waits, 95.0)),
        opt(percentile(&waits, 100.0)),
        waits.len(),
        waits.iter().filter(|&&w| w > WAIT_P95_S).count(),
    );

    let mut lines: Vec<(String, bool)> = groups.iter().flat_map(group_criteria).collect();
    let delay_p95 = percentile(&delays, 95.0).unwrap_or(0.0);
    let stop_p95 = percentile(&stops, 95.0).unwrap_or(0.0);
    let cost = pass_cost_of(&runs);
    lines.push((
        format!("4 commit delay p95 {delay_p95:.2} s ≤ {COMMIT_DELAY_P95_S} s"),
        delay_p95 <= COMMIT_DELAY_P95_S,
    ));
    let wait_p95 = percentile(&waits, 95.0).unwrap_or(0.0);
    let wait_max = percentile(&waits, 100.0).unwrap_or(0.0);
    lines.push((
        format!("4 first-word wait p95 {wait_p95:.2} s ≤ {WAIT_P95_S} s, max {wait_max:.2} s ≤ {WAIT_MAX_S} s"),
        wait_p95 <= WAIT_P95_S && wait_max <= WAIT_MAX_S,
    ));
    lines.push((
        format!("4 stop latency p95 {stop_p95:.2} s ≤ {STOP_LATENCY_P95_S} s"),
        stop_p95 <= STOP_LATENCY_P95_S,
    ));
    lines.push((
        format!("4 mean pass cost {cost:.2} ≤ {PASS_COST_MAX}"),
        cost <= PASS_COST_MAX,
    ));
    let memory = memory_in_fresh_process()?;
    lines.push((
        format!(
            "5 {DICTATION_SECONDS:.0} s dictation through the rolling streamer ≤ 1.5 GB \
             (peak RSS {:.2} GB, peak physical footprint {:.2} GB, {} passes, {:.1} s)",
            memory.0 as f64 / 1e9,
            memory.1 as f64 / 1e9,
            memory.2,
            memory.3
        ),
        memory.0 <= MEMORY_TARGET_BYTES && memory.1 <= MEMORY_TARGET_BYTES,
    ));

    println!("\ncriteria");
    for (line, is_met) in &lines {
        println!("  {} {line}", mark(*is_met));
    }
    Ok(if lines.iter().all(|(_, is_met)| *is_met) {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    })
}

// --- memory -----------------------------------------------------------------

/// Child side: a long dictation fed to the rolling streamer at the 50 ms beat,
/// passes run as soon as they are due. Prints
/// `rss_bytes<TAB>footprint_bytes<TAB>passes<TAB>seconds`.
pub fn memory_probe() -> Result<ExitCode, String> {
    let dictation = corpus::long_dictation(DICTATION_SECONDS)?;
    let mut pipeline = Pipeline::load_default().map_err(|error| error.to_string())?;
    let started = Instant::now();
    let mut streamer = Streamer::new();
    let mut passes = 0;
    for block in dictation.chunks(BLOCK) {
        streamer.push(block);
        if streamer.is_pass_due() {
            streamer
                .pass(&mut pipeline)
                .map_err(|error| error.to_string())?;
            passes += 1;
        }
    }
    streamer
        .finish(&mut pipeline)
        .map_err(|error| error.to_string())?;
    println!(
        "{}\t{}\t{}\t{:.2}",
        memory::peak_rss_bytes(),
        memory::peak_footprint_bytes(),
        passes,
        started.elapsed().as_secs_f64()
    );
    Ok(ExitCode::SUCCESS)
}

fn memory_in_fresh_process() -> Result<(u64, u64, usize, f64), String> {
    let exe = std::env::current_exe().map_err(|error| error.to_string())?;
    let output = std::process::Command::new(exe)
        .arg("--streaming-memory-probe")
        .output()
        .map_err(|error| format!("streaming memory probe: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let fields: Vec<&str> = stdout.trim().split('\t').collect();
    let parse_error =
        || format!("streaming memory probe printed {stdout:?}, expected 4 tab-separated numbers");
    match (output.status.success(), fields.as_slice()) {
        (true, [rss, footprint, passes, seconds]) => Ok((
            rss.parse().map_err(|_| parse_error())?,
            footprint.parse().map_err(|_| parse_error())?,
            passes.parse().map_err(|_| parse_error())?,
            seconds.parse().map_err(|_| parse_error())?,
        )),
        _ => Err(format!(
            "streaming memory probe failed ({}): {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use whispy_core::stream::PassStats;

    #[test]
    fn counts_sentence_ends() {
        assert_eq!(sentence_ends("Un. Deux ? Trois ! Quatre…"), 4);
        assert_eq!(sentence_ends("pas de ponctuation, ou presque"), 0);
        assert_eq!(extra_sentence_ends("a. b. c.", "a. b."), 1);
        assert_eq!(extra_sentence_ends("a.", "a. b. c."), 0);
    }

    #[test]
    fn percentile_is_nearest_rank() {
        let values = [4.0, 1.0, 3.0, 2.0, 5.0];
        assert_eq!(percentile(&values, 50.0), Some(3.0));
        assert_eq!(percentile(&values, 95.0), Some(5.0));
        assert_eq!(percentile(&values, 0.0), Some(1.0));
        assert_eq!(percentile(&[7.0], 95.0), Some(7.0));
        assert_eq!(percentile(&[], 50.0), None);
    }

    #[test]
    fn thinking_pause_goes_in_the_longest_inner_gap_of_the_first_half() {
        // leading silence (ignored), speech, 2-frame gap, speech, 5-frame gap, speech...
        let mut voiced = vec![false; 6];
        voiced.extend([true; 3]);
        voiced.extend([false; 2]);
        voiced.extend([true; 3]);
        voiced.extend([false; 5]);
        voiced.extend([true; 3]);
        voiced.extend([true; 20]);
        assert_eq!(longest_gap_middle(&voiced, voiced.len() / 2), Some(16));
        // A gap past the limit is not considered.
        assert_eq!(longest_gap_middle(&voiced, 13), Some(10));
        assert_eq!(longest_gap_middle(&[false; 10], 5), None);
    }

    /// A worker whose passes cost a fixed time and which types a word per pass.
    struct Fake {
        pushed: usize,
        since_pass: usize,
        cost: f64,
        finish_cost: f64,
        passes: usize,
    }

    impl Worker for Fake {
        fn push(&mut self, samples: &[f32]) {
            self.pushed += samples.len();
            self.since_pass += samples.len();
        }
        fn is_pass_due(&self) -> bool {
            self.since_pass >= SAMPLE_RATE as usize * 6 / 10
        }
        fn pass(&mut self) -> Result<(Update, f64), Error> {
            self.since_pass = 0;
            self.passes += 1;
            Ok((
                Update {
                    typed: " mot".to_string(),
                    provisional: String::new(),
                    stats: PassStats {
                        audio_end_s: self.pushed as f32 / SAMPLE_RATE as f32 - 0.5,
                        forced: self.passes == 2,
                        ..PassStats::default()
                    },
                },
                self.cost,
            ))
        }
        fn finish(self) -> Result<(String, f64), Error> {
            Ok((" fin".to_string(), self.finish_cost))
        }
    }

    fn fake(cost: f64) -> Fake {
        Fake {
            pushed: 0,
            since_pass: 0,
            cost,
            finish_cost: 0.25,
            passes: 0,
        }
    }

    #[test]
    fn a_fast_worker_types_at_pass_end_and_stops_at_once() {
        // 3 s of audio, passes every 0.6 s costing 0.1 s: 5 passes.
        let run = simulate(fake(0.1), &vec![0.0; SAMPLE_RATE as usize * 3]).unwrap();
        assert_eq!(run.pass_times.len(), 5);
        assert_eq!(run.text, " mot mot mot mot mot fin");
        assert_eq!(run.forced, 1);
        // Commit delay: 0.5 s of audio behind the clock plus the pass time.
        assert!(run.commit_delays.iter().all(|d| (d - 0.6).abs() < 1e-3));
        // The last pass ends at 3.1 s, 0.1 s after the stop: it waits, then the finish.
        assert!((run.stop_latency - 0.35).abs() < 1e-3);
        assert!((run.audio_s - 3.0).abs() < 1e-6);
    }

    #[test]
    fn a_slow_worker_skips_blocks_and_delays_the_stop() {
        // Passes cost 1.5 s: the worker is busy through the next due points.
        let run = simulate(fake(1.5), &vec![0.0; SAMPLE_RATE as usize * 3]).unwrap();
        // t=0.6 pass (busy to 2.1), next at t>=2.1 (due since 0.6): 2.1, busy to 3.6.
        assert_eq!(run.pass_times.len(), 2);
        // Stop at 3.0 while busy until 3.6, then the 0.25 s finish.
        assert!((run.stop_latency - (0.6 + 0.25)).abs() < 1e-3);
        assert!((run.commit_delays[0] - 2.0).abs() < 1e-3);
    }
}

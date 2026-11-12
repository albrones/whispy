//! « Type while speaking »: a dictation cut at its pauses while it records,
//! each piece transcribed on its own, against the same audio in one block.
//!
//! `banc --streaming` composes two French reference sentences with one second
//! of silence between them, feeds it to [`LiveSplitter`] 50 ms at a time as
//! the microphone does, transcribes each piece with the default pipeline, and
//! compares the joined text's WER with one-block transcription. Then, in a
//! fresh process, a 180 s dictation goes the same way and its peak memory is
//! measured. Exit 1 when a criterion fails.

use std::process::ExitCode;
use std::time::Instant;

use whispy_core::audio::{self, SAMPLE_RATE};
use whispy_core::split::LiveSplitter;
use whispy_core::Pipeline;

use crate::{corpus, memory, wer};

const FIRST: (&str, &str) = (
    "fr-sentence-rapport.wav",
    "je vais envoyer le rapport à l'équipe demain matin avant la réunion",
);
const SECOND: (&str, &str) = (
    "fr-sentence-courses.wav",
    "pense à acheter du pain et des tomates en rentrant ce soir",
);
const PAUSE_S: f32 = 1.0;
/// 50 ms at 16 kHz: the beat at which the app drains the microphone.
const BLOCK: usize = 800;
const DICTATION_SECONDS: f32 = 180.0;
const MEMORY_TARGET_BYTES: u64 = 1_500_000_000;

pub fn run() -> Result<ExitCode, String> {
    let clip = two_sentences()?;
    let expected = format!("{} {}", FIRST.1, SECOND.1);
    let mut pipeline = Pipeline::load_default().map_err(|error| error.to_string())?;

    let pieces = split_as_recorded(&clip);
    let mut texts = Vec::new();
    let mut offset_s = 0.0;
    for (index, piece) in pieces.iter().enumerate() {
        let text = pipeline
            .transcribe(piece)
            .map_err(|error| error.to_string())?
            .text;
        let seconds = audio::seconds(piece);
        println!(
            "piece {}: {offset_s:.2}–{:.2} s  {text:?}",
            index + 1,
            offset_s + seconds
        );
        offset_s += seconds;
        if !text.trim().is_empty() {
            texts.push(text.trim().to_string());
        }
    }
    let joined = texts.join(" ");
    let block = pipeline
        .transcribe(&clip)
        .map_err(|error| error.to_string())?
        .text;
    let joined_wer = word_error_rate(&expected, &joined);
    let block_wer = word_error_rate(&expected, &block);
    println!("expected: {expected:?}");
    println!("joined:   {joined:?}  WER {:.1} %", joined_wer * 100.0);
    println!("block:    {block:?}  WER {:.1} %", block_wer * 100.0);

    let has_two_pieces = texts.len() >= 2;
    let is_no_worse = joined_wer <= block_wer;
    println!(
        "criterion 2 (≥ 2 pieces with text, in order): {} ({} pieces with text)",
        verdict(has_two_pieces),
        texts.len()
    );
    println!(
        "criterion 3 (joined WER ≤ one-block WER): {}",
        verdict(is_no_worse)
    );

    let memory = memory_in_fresh_process()?;
    let is_within_memory = memory.0 <= MEMORY_TARGET_BYTES && memory.1 <= MEMORY_TARGET_BYTES;
    println!(
        "criterion 5 ({DICTATION_SECONDS:.0} s dictation typed while spoken, ≤ 1.5 GB): {} \
         (peak RSS {:.2} GB, peak physical footprint {:.2} GB, {} pieces, {:.1} s)",
        verdict(is_within_memory),
        memory.0 as f64 / 1e9,
        memory.1 as f64 / 1e9,
        memory.2,
        memory.3
    );
    Ok(if has_two_pieces && is_no_worse && is_within_memory {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    })
}

/// Child side: a long dictation cut and transcribed piece by piece. Prints
/// `rss_bytes<TAB>footprint_bytes<TAB>pieces<TAB>seconds`.
pub fn memory_probe() -> Result<ExitCode, String> {
    let dictation = corpus::long_dictation(DICTATION_SECONDS)?;
    let mut pipeline = Pipeline::load_default().map_err(|error| error.to_string())?;
    let started = Instant::now();
    let pieces = split_as_recorded(&dictation);
    for piece in &pieces {
        pipeline
            .transcribe(piece)
            .map_err(|error| error.to_string())?;
    }
    println!(
        "{}\t{}\t{}\t{:.2}",
        memory::peak_rss_bytes(),
        memory::peak_footprint_bytes(),
        pieces.len(),
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
        (true, [rss, footprint, pieces, seconds]) => Ok((
            rss.parse().map_err(|_| parse_error())?,
            footprint.parse().map_err(|_| parse_error())?,
            pieces.parse().map_err(|_| parse_error())?,
            seconds.parse().map_err(|_| parse_error())?,
        )),
        _ => Err(format!(
            "streaming memory probe failed ({}): {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        )),
    }
}

/// The pieces the app would queue: closed while recording, then the rest at the stop.
fn split_as_recorded(samples: &[f32]) -> Vec<Vec<f32>> {
    let mut splitter = LiveSplitter::new();
    let mut pieces = Vec::new();
    for block in samples.chunks(BLOCK) {
        pieces.extend(splitter.push(block));
    }
    pieces.push(splitter.finish());
    pieces
}

fn two_sentences() -> Result<Vec<f32>, String> {
    let dir = corpus::bench_dir().join("reference");
    let read = |file: &str| audio::read_wav(&dir.join(file)).map_err(|error| error.to_string());
    let pause = vec![0.0; (PAUSE_S * SAMPLE_RATE as f32) as usize];
    Ok([read(FIRST.0)?, pause, read(SECOND.0)?].concat())
}

fn word_error_rate(expected: &str, actual: &str) -> f64 {
    let expected = wer::normalized_words(expected);
    let actual = wer::normalized_words(actual);
    wer::word_edits(&expected, &actual) as f64 / expected.len() as f64
}

fn verdict(is_met: bool) -> &'static str {
    if is_met {
        "met"
    } else {
        "NOT met"
    }
}

//! The Whispy V2 bench: `cargo run --release --bin banc` (from v2/).
//!
//! Replays the clips V1 lost and a reference set with a known text through
//! every engine and strategy, runs V1 on the same clips, measures the memory
//! of a 180 s dictation, and writes `bench/REPORT.md` with the pick.

mod corpus;
mod labelled;
mod measure;
mod memory;
mod oracle;
mod report;
mod v1;
mod wer;

use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use whispy_core::{EngineKind, Pipeline, Strategy};

use crate::measure::Config;

const DICTATION_SECONDS: f32 = 180.0;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("--memory-probe") => memory_probe(&args[1..]),
        Some("--lazy-probe") => memory::lazy_probe(DICTATION_SECONDS).map(|usage| {
            println!("{}", usage.line());
            ExitCode::SUCCESS
        }),
        Some("--labelled") => labelled::run(&args[1..]),
        Some("--transcribe") => transcribe_files(&args[1..]),
        Some("--help") | Some("-h") => {
            println!("{}", usage());
            Ok(ExitCode::SUCCESS)
        }
        _ => run(args.iter().any(|arg| arg == "--skip-v1")),
    };
    result.unwrap_or_else(|message| {
        eprintln!("banc: {message}");
        ExitCode::FAILURE
    })
}

fn usage() -> &'static str {
    "usage: banc [--skip-v1]\n       banc --labelled [dir]   (criterion 3 on your labelled clips, default ~/.whispy/bench)\n       banc --transcribe <parakeet|whisper> <raw|gated|louder|padded> <clip.wav>...\n\n\
     Env: WHISPY_LOST_DIR (default ~/.whispy/lost), WHISPY_V1_PYTHON (default <repo>/.venv/bin/python),\n     \
     WHISPY_PARAKEET_DIR, WHISPY_WHISPER_MODEL (default: the files V1 and Jarvis already downloaded)."
}

pub fn engine_named(name: &str) -> Result<EngineKind, String> {
    EngineKind::ALL
        .into_iter()
        .find(|engine| engine.name() == name)
        .ok_or_else(|| format!("unknown engine {name:?}, expected parakeet or whisper"))
}

pub fn strategy_named(name: &str) -> Result<Strategy, String> {
    Strategy::ALL
        .into_iter()
        .find(|strategy| strategy.name() == name)
        .ok_or_else(|| format!("unknown strategy {name:?}, expected raw, gated, louder or padded"))
}

fn run(skip_v1: bool) -> Result<ExitCode, String> {
    let work_dir = std::env::temp_dir().join(format!("whispy-banc-{}", std::process::id()));
    std::fs::create_dir_all(&work_dir)
        .map_err(|error| format!("{}: {error}", work_dir.display()))?;
    let outcome = run_in(&work_dir, skip_v1);
    // The work directory holds copies of voice clips: never leave it behind.
    let _ = std::fs::remove_dir_all(&work_dir);
    outcome
}

fn run_in(work_dir: &std::path::Path, skip_v1: bool) -> Result<ExitCode, String> {
    let clips = corpus::load(work_dir)?;
    eprintln!(
        "banc: {} clips loaded ({} lost from {})",
        clips.len(),
        clips
            .iter()
            .filter(|c| c.group == corpus::Group::Lost)
            .count(),
        corpus::lost_dir().display()
    );

    let runs = measure::run_engines(&clips)?;

    let v1 = if skip_v1 {
        Err("skipped (--skip-v1)".to_string())
    } else {
        eprintln!("banc: V1 on the same clips ({})", v1::python().display());
        let paths: Vec<PathBuf> = clips
            .iter()
            .flat_map(|clip| std::iter::repeat_n(clip.path.clone(), measure::repeats(clip)))
            .collect();
        v1::transcribe(&paths, work_dir)
    };

    let mut memory = Vec::new();
    let default = Config::library_default();
    // Each engine alone; the default pipeline, whose fallback loads lazily,
    // is probed apart by `spawn_lazy_probe`.
    for primary in EngineKind::ALL {
        let config = Config {
            primary,
            fallback: None,
            strategy: default.strategy,
        };
        eprintln!(
            "banc: memory of a {DICTATION_SECONDS:.0} s dictation, {}",
            config.label()
        );
        memory.push((config, spawn_memory_probe(&config)));
    }
    eprintln!(
        "banc: default pipeline: {DICTATION_SECONDS:.0} s dictation, two reprises, then {} s idle",
        whispy_core::FALLBACK_IDLE.as_secs()
    );
    let lazy = spawn_lazy_probe();
    let oracle = oracle::load();

    let report = report::Report::build(&clips, &runs, v1, memory, lazy, oracle);
    let path = corpus::bench_dir().join("REPORT.md");
    std::fs::write(&path, report.markdown())
        .map_err(|error| format!("{}: {error}", path.display()))?;
    println!("{}", report.summary());
    println!("Report written to {}", path.display());
    if report.pick() != default {
        eprintln!(
            "banc: the bench picks {} but whispy_core defaults to {}: update DEFAULT_ENGINE/DEFAULT_FALLBACK/DEFAULT_STRATEGY",
            report.pick().label(),
            default.label()
        );
        return Ok(ExitCode::from(2));
    }
    Ok(ExitCode::SUCCESS)
}

/// The default pipeline's memory and reprise latency, in a fresh process.
fn spawn_lazy_probe() -> Result<memory::LazyUse, String> {
    let exe = std::env::current_exe().map_err(|error| error.to_string())?;
    let output = std::process::Command::new(exe)
        .arg("--lazy-probe")
        .output()
        .map_err(|error| format!("lazy probe: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "lazy probe failed ({}): {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    memory::LazyUse::parse(&String::from_utf8_lossy(&output.stdout))
}

/// Peak memory of a dictation, measured in a fresh process so engines loaded
/// earlier do not count.
fn spawn_memory_probe(config: &Config) -> Result<report::MemoryUse, String> {
    let exe = std::env::current_exe().map_err(|error| error.to_string())?;
    let output = std::process::Command::new(exe)
        .arg("--memory-probe")
        .arg(config.primary.name())
        .arg(config.fallback.map_or("none", EngineKind::name))
        .arg(config.strategy.name())
        .output()
        .map_err(|error| format!("memory probe: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let fields: Vec<&str> = stdout.trim().split('\t').collect();
    match (output.status.success(), fields.as_slice()) {
        (true, [rss, footprint, seconds, characters]) => Ok(report::MemoryUse {
            peak_rss_bytes: rss.parse().map_err(|_| format!("probe RSS {rss:?}"))?,
            peak_footprint_bytes: footprint
                .parse()
                .map_err(|_| format!("probe footprint {footprint:?}"))?,
            seconds: seconds
                .parse()
                .map_err(|_| format!("probe seconds {seconds:?}"))?,
            characters: characters
                .parse()
                .map_err(|_| format!("probe characters {characters:?}"))?,
        }),
        _ => Err(format!(
            "memory probe failed ({}): {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        )),
    }
}

/// Child side of the memory probe: prints
/// `rss_bytes<TAB>footprint_bytes<TAB>seconds<TAB>characters`.
fn memory_probe(args: &[String]) -> Result<ExitCode, String> {
    let [primary, fallback, strategy] = args else {
        return Err("--memory-probe takes <engine> <engine|none> <strategy>".to_string());
    };
    let primary = engine_named(primary)?
        .load()
        .map_err(|error| error.to_string())?;
    let fallback = match fallback.as_str() {
        "none" => None,
        name => Some(
            engine_named(name)?
                .load()
                .map_err(|error| error.to_string())?,
        ),
    };
    let dictation = corpus::long_dictation(DICTATION_SECONDS)?;
    let mut pipeline = Pipeline::new(primary, fallback, strategy_named(strategy)?);
    let started = Instant::now();
    let transcript = pipeline
        .transcribe(&dictation)
        .map_err(|error| error.to_string())?;
    let seconds = started.elapsed().as_secs_f64();
    println!(
        "{}\t{}\t{seconds:.2}\t{}",
        memory::peak_rss_bytes(),
        memory::peak_footprint_bytes(),
        transcript.text.chars().count()
    );
    Ok(ExitCode::SUCCESS)
}

/// Debug helper: one engine and strategy on given files.
fn transcribe_files(args: &[String]) -> Result<ExitCode, String> {
    let [engine, strategy, files @ ..] = args else {
        return Err(usage().to_string());
    };
    let strategy = strategy_named(strategy)?;
    let mut engine = engine_named(engine)?
        .load()
        .map_err(|error| error.to_string())?;
    for file in files {
        let samples = whispy_core::audio::read_wav(std::path::Path::new(file))
            .map_err(|error| error.to_string())?;
        let started = Instant::now();
        let text = match strategy.prepare(&samples) {
            Some(input) => engine
                .transcribe(&input)
                .map_err(|error| error.to_string())?,
            None => String::new(),
        };
        println!("{file}\t{:.3}s\t{text:?}", started.elapsed().as_secs_f64());
    }
    Ok(ExitCode::SUCCESS)
}

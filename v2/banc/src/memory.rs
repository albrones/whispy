//! Process memory, and the probe of the default pipeline with its lazy fallback.

use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use whispy_core::pipeline::DEFAULT_FALLBACK;
use whispy_core::{Error, Pipeline, Transcriber, DEFAULT_STRATEGY, FALLBACK_IDLE};

use crate::corpus;

fn rusage() -> Option<libc::rusage_info_v4> {
    let mut info: libc::rusage_info_v4 = unsafe { std::mem::zeroed() };
    // SAFETY: proc_pid_rusage writes one rusage_info_v4 into the struct we own.
    let status = unsafe {
        libc::proc_pid_rusage(
            std::process::id() as libc::c_int,
            libc::RUSAGE_INFO_V4,
            &mut info as *mut libc::rusage_info_v4 as *mut libc::rusage_info_t,
        )
    };
    (status == 0).then_some(info)
}

/// Lifetime peak physical footprint (what macOS memory pressure counts,
/// Metal buffers included), in bytes; 0 when unavailable.
pub fn peak_footprint_bytes() -> u64 {
    rusage().map_or(0, |info| info.ri_lifetime_max_phys_footprint)
}

/// Physical footprint right now, in bytes; 0 when unavailable.
pub fn footprint_bytes() -> u64 {
    rusage().map_or(0, |info| info.ri_phys_footprint)
}

/// Resident size right now, in bytes; 0 when unavailable.
pub fn rss_bytes() -> u64 {
    rusage().map_or(0, |info| info.ri_resident_size)
}

pub fn peak_rss_bytes() -> u64 {
    let mut usage: libc::rusage = unsafe { std::mem::zeroed() };
    // SAFETY: getrusage only writes into the struct we own.
    let status = unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut usage) };
    if status != 0 {
        return 0;
    }
    // macOS reports ru_maxrss in bytes (Linux in kilobytes).
    if cfg!(target_os = "macos") {
        usage.ru_maxrss as u64
    } else {
        usage.ru_maxrss as u64 * 1024
    }
}

/// The primary engine, made to return nothing on demand: Parakeet still runs
/// (its memory and time count), and the pipeline turns to the fallback as it
/// would on a real miss.
struct Muted {
    inner: Box<dyn Transcriber>,
    is_muted: Arc<AtomicBool>,
}

impl Transcriber for Muted {
    fn name(&self) -> &'static str {
        self.inner.name()
    }
    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
        let text = self.inner.transcribe(samples)?;
        Ok(if self.is_muted.load(Ordering::SeqCst) {
            String::new()
        } else {
            text
        })
    }
}

/// What the default pipeline costs, phase by phase (criterion 5).
pub struct LazyUse {
    /// Lifetime peaks after a 180 s dictation the primary engine answered alone.
    pub normal_peak_footprint: u64,
    pub normal_peak_rss: u64,
    /// Whether that dictation needed the fallback (it should not).
    pub normal_loaded_fallback: bool,
    /// One ~5 s sentence the primary misses: the fallback loads, then answers.
    pub cold_reprise_s: f64,
    /// The same sentence again, fallback already loaded.
    pub warm_reprise_s: f64,
    pub reprise_peak_footprint: u64,
    pub reprise_peak_rss: u64,
    /// Whether the fallback was freed after `FALLBACK_IDLE` and a margin.
    pub is_released: bool,
    pub released_footprint: u64,
    pub released_rss: u64,
}

impl LazyUse {
    const FIELDS: usize = 11;

    pub fn line(&self) -> String {
        format!(
            "{}\t{}\t{}\t{:.3}\t{:.3}\t{}\t{}\t{}\t{}\t{}\t{}",
            self.normal_peak_footprint,
            self.normal_peak_rss,
            u8::from(self.normal_loaded_fallback),
            self.cold_reprise_s,
            self.warm_reprise_s,
            self.reprise_peak_footprint,
            self.reprise_peak_rss,
            u8::from(self.is_released),
            self.released_footprint,
            self.released_rss,
            FALLBACK_IDLE.as_secs()
        )
    }

    pub fn parse(line: &str) -> Result<Self, String> {
        let fields: Vec<&str> = line.trim().split('\t').collect();
        if fields.len() != Self::FIELDS {
            return Err(format!(
                "lazy probe printed {} fields, expected {}: {line:?}",
                fields.len(),
                Self::FIELDS
            ));
        }
        let number = |index: usize| -> Result<f64, String> {
            fields[index]
                .parse::<f64>()
                .map_err(|_| format!("lazy probe field {index} is {:?}", fields[index]))
        };
        Ok(LazyUse {
            normal_peak_footprint: number(0)? as u64,
            normal_peak_rss: number(1)? as u64,
            normal_loaded_fallback: number(2)? != 0.0,
            cold_reprise_s: number(3)?,
            warm_reprise_s: number(4)?,
            reprise_peak_footprint: number(5)? as u64,
            reprise_peak_rss: number(6)? as u64,
            is_released: number(7)? != 0.0,
            released_footprint: number(8)? as u64,
            released_rss: number(9)? as u64,
        })
    }
}

/// Child side of the lazy probe: the default pipeline through a normal 180 s
/// dictation, two reprises, then `FALLBACK_IDLE` of quiet.
pub fn lazy_probe(dictation_seconds: f32) -> Result<LazyUse, String> {
    let to_text = |error: Error| error.to_string();
    let is_muted = Arc::new(AtomicBool::new(false));
    let primary = Muted {
        inner: whispy_core::DEFAULT_ENGINE.load().map_err(to_text)?,
        is_muted: Arc::clone(&is_muted),
    };
    let fallback = DEFAULT_FALLBACK
        .ok_or("the default pipeline has no fallback engine to probe")?
        .lazy(FALLBACK_IDLE)
        .map_err(to_text)?;
    let fallback_name = fallback.name();
    let mut pipeline = Pipeline::new(
        Box::new(primary),
        Some(Box::new(fallback.clone())),
        DEFAULT_STRATEGY,
    );

    let dictation = corpus::long_dictation(dictation_seconds)?;
    pipeline.transcribe(&dictation).map_err(to_text)?;
    let normal_peak_footprint = peak_footprint_bytes();
    let normal_peak_rss = peak_rss_bytes();
    let normal_loaded_fallback = fallback.is_loaded();

    let sentence = whispy_core::audio::read_wav(
        &corpus::bench_dir().join(Path::new("reference/fr-sentence-rapport.wav")),
    )
    .map_err(to_text)?;
    is_muted.store(true, Ordering::SeqCst);
    let mut timed = || -> Result<f64, String> {
        let started = Instant::now();
        let transcript = pipeline.transcribe(&sentence).map_err(to_text)?;
        if transcript.engine != Some(fallback_name) {
            return Err(format!(
                "the reprise was answered by {:?}, expected {fallback_name}",
                transcript.engine
            ));
        }
        Ok(started.elapsed().as_secs_f64())
    };
    let cold_reprise_s = timed()?;
    let warm_reprise_s = timed()?;
    let reprise_peak_footprint = peak_footprint_bytes();
    let reprise_peak_rss = peak_rss_bytes();

    std::thread::sleep(FALLBACK_IDLE + Duration::from_secs(2));
    Ok(LazyUse {
        normal_peak_footprint,
        normal_peak_rss,
        normal_loaded_fallback,
        cold_reprise_s,
        warm_reprise_s,
        reprise_peak_footprint,
        reprise_peak_rss,
        is_released: !fallback.is_loaded(),
        released_footprint: footprint_bytes(),
        released_rss: rss_bytes(),
    })
}

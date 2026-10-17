//! Criterion 4, end to end: from Fn released to the text handed to the
//! inserter, p95 under 1.5 s for a dictation of at least 5 s.
//!
//! The whole app path runs — state machine, controller and worker threads,
//! resampling from 48 kHz, the default pipeline with the real models — with
//! two stand-ins: a WAV plays the microphone's part and a recorder plays the
//! inserter's (real insertion needs Accessibility; see the README).
//!
//! Needs the models on this Mac, so it is ignored by default:
//!     cargo test --release -p whispy2 --test latency -- --ignored --nocapture

use std::path::Path;
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use whispy2::controller::{Capture, Controller, Inserter, LostClips, Status, LOADING_NOTE};
use whispy2::machine::{Delivery, Event, State};
use whispy2::resample;
use whispy_core::audio::{read_wav, SAMPLE_RATE};
use whispy_core::Pipeline;

const TARGET_P95: Duration = Duration::from_millis(1_500);
const REPEATS: usize = 10;
const DEVICE_RATE: u32 = 48_000;
/// Two reference sentences back to back: 6–7 s of speech, more than the 5 s
/// of the criterion, so the measure errs on the slow side.
const DICTATIONS: [(&str, &str); 4] = [
    ("fr-sentence-rapport.wav", "fr-sentence-courses.wav"),
    ("fr-sentence-train-jacques.wav", "fr-sentence-mixed.wav"),
    ("en-sentence-report.wav", "en-sentence-groceries.wav"),
    ("en-sentence-groceries.wav", "en-sentence-train-daniel.wav"),
];

/// Plays a clip as a 48 kHz microphone would deliver it, resampled on stop
/// exactly like the real one.
struct WavMicrophone {
    next_clip: Arc<Mutex<Vec<f32>>>,
}

impl Capture for WavMicrophone {
    fn start(&mut self) -> Result<(), String> {
        Ok(())
    }
    fn stop(&mut self) -> Vec<f32> {
        let device_audio = self.next_clip.lock().unwrap().clone();
        resample::to_16k_mono(&device_audio, 1, DEVICE_RATE)
    }
}

struct RecordingInserter(Sender<(String, Instant)>);

impl Inserter for RecordingInserter {
    fn deliver(&mut self, text: &str, _delivery: Delivery) -> Result<(), String> {
        let _ = self.0.send((text.to_string(), Instant::now()));
        Ok(())
    }
}

fn reference(name: &str) -> Vec<f32> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../bench/reference")
        .join(name);
    read_wav(&path).unwrap_or_else(|error| panic!("{}: {error}", path.display()))
}

/// 16 kHz → 48 kHz by repeating samples: the resampler's filter then has real work to do.
fn as_device_audio(samples: &[f32]) -> Vec<f32> {
    let factor = (DEVICE_RATE / SAMPLE_RATE) as usize;
    samples
        .iter()
        .flat_map(|sample| std::iter::repeat_n(*sample, factor))
        .collect()
}

fn wait_for(statuses: &Receiver<Status>, is_wanted: impl Fn(&Status) -> bool) -> Status {
    loop {
        let status = statuses
            .recv_timeout(Duration::from_secs(120))
            .expect("the app stopped reporting its status");
        if is_wanted(&status) {
            return status;
        }
    }
}

fn percentile(sorted: &[Duration], percent: f64) -> Duration {
    let rank = ((percent / 100.0) * (sorted.len() - 1) as f64).round() as usize;
    sorted[rank]
}

#[test]
#[ignore = "needs the Parakeet and whisper models on this Mac"]
fn release_to_insertion_p95_is_under_one_and_a_half_seconds() {
    let next_clip = Arc::new(Mutex::new(Vec::new()));
    let microphone_clip = Arc::clone(&next_clip);
    let (inserted, insertions) = mpsc::channel();
    let (status_sender, statuses) = mpsc::channel();
    let controller = Controller::start(
        move || WavMicrophone {
            next_clip: microphone_clip,
        },
        Pipeline::load_default,
        RecordingInserter(inserted),
        LostClips { directory: None },
        move |status: &Status| {
            let _ = status_sender.send(status.clone());
        },
    );
    let loaded = wait_for(&statuses, |status| {
        status.note.as_deref() != Some(LOADING_NOTE)
    });
    assert!(loaded.note.is_none(), "{:?}", loaded.note);

    let mut latencies = Vec::new();
    let mut first_dictation = None;
    for (first, second) in DICTATIONS {
        let mut speech = reference(first);
        speech.extend(std::iter::repeat_n(0.0, SAMPLE_RATE as usize * 3 / 10));
        speech.extend(reference(second));
        let seconds = speech.len() as f64 / SAMPLE_RATE as f64;
        assert!(seconds >= 5.0, "{first} + {second}: {seconds:.1} s");
        *next_clip.lock().unwrap() = as_device_audio(&speech);
        for _ in 0..=REPEATS {
            let pressed = Instant::now() - Duration::from_secs_f64(seconds);
            controller.send(Event::FnDown(pressed));
            let released = Instant::now();
            controller.send(Event::FnUp(released));
            let (text, at) = insertions
                .recv_timeout(Duration::from_secs(60))
                .expect("no text was inserted");
            assert!(!text.is_empty());
            let latency = at - released;
            match first_dictation {
                // The first call pays one-off allocations; reported, not counted.
                None => first_dictation = Some(latency),
                Some(_) => latencies.push(latency),
            }
            wait_for(&statuses, |status| status.state == State::Idle);
        }
        println!("{first} + {second} ({seconds:.1} s)");
    }
    controller.stop();

    latencies.sort();
    let p50 = percentile(&latencies, 50.0);
    let p95 = percentile(&latencies, 95.0);
    let max = *latencies.last().unwrap();
    println!(
        "release → insertion over {} dictations: p50 {:.3} s, p95 {:.3} s, max {:.3} s; first dictation after loading {:.3} s",
        latencies.len(),
        p50.as_secs_f64(),
        p95.as_secs_f64(),
        max.as_secs_f64(),
        first_dictation.unwrap().as_secs_f64()
    );
    assert!(p95 < TARGET_P95, "p95 {p95:?} is over {TARGET_P95:?}");
}

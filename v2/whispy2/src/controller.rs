//! Runs the state machine against the outside world.
//!
//! Two threads. The controller thread owns the [`Machine`], the microphone and
//! the [`Feedback`], and never blocks on a model: it only reacts to inputs. The
//! worker thread owns the [`Pipeline`] and the inserter, and runs one job at a
//! time (load the models, transcribe a dictation, insert its text), reporting
//! each result back to the controller as an event. A release is therefore never
//! waiting behind a transcription, and a transcription never runs twice at once.
//!
//! The worker also writes the journal: it is the one that knows the outcome and
//! the moment the text was delivered.

use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use whispy_core::{Pipeline, Strategy};

use crate::feedback::{phase_of, Feedback, Phase};
use crate::journal::{Entry, Journal, Outcome};
use crate::log;
use crate::machine::{Action, Delivery, Event, Machine, Mode, State};

/// Where the audio-level updates of a recording go (see [`Capture::set_level_sink`]).
pub type LevelSink = Arc<dyn Fn(f32) + Send + Sync>;

/// The microphone, as the controller sees it: 16 kHz mono out.
pub trait Capture {
    fn start(&mut self) -> Result<(), String>;
    /// Stops the recording and returns it, 16 kHz mono `f32`.
    fn stop(&mut self) -> Vec<f32>;
    /// The name of the device the last recording used, once started.
    fn device_name(&self) -> Option<String> {
        None
    }
    /// Where to push the block level while recording, about 20 times a second.
    /// Called once, before the first recording.
    fn set_level_sink(&mut self, _sink: LevelSink) {}
}

/// Puts text where the user is.
pub trait Inserter: Send {
    fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String>;
}

/// What triggered an edge: the Fn key or the control socket. Only the
/// controller looks at it (for the journal); the machine never does.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Source {
    Fn,
    Socket,
}

impl Source {
    pub fn as_str(self) -> &'static str {
        match self {
            Source::Fn => "fn",
            Source::Socket => "socket",
        }
    }
}

/// What the menu shows.
#[derive(Debug, Clone, PartialEq)]
pub struct Status {
    pub state: State,
    /// The last thing worth telling the user (loading, an error), if any.
    pub note: Option<String>,
    pub models_loaded: bool,
}

impl Status {
    pub fn headline(&self) -> &'static str {
        match self.state {
            State::Idle => "Ready — hold Fn to dictate, tap it to toggle",
            State::Recording {
                mode: Mode::Hold, ..
            } => "Recording — release Fn to insert",
            State::Recording {
                mode: Mode::Toggle, ..
            } => "Recording — press Fn to stop",
            State::Transcribing { .. } => "Transcribing…",
            State::Inserting => "Inserting…",
            State::Yielded => "Whispy V1 is running — Fn is left to it",
        }
    }

    /// A stable word for scripts (the socket's `status` reply).
    pub fn state_name(&self) -> &'static str {
        match self.state {
            State::Idle => "idle",
            State::Recording { .. } => "recording",
            State::Transcribing { .. } => "transcribing",
            State::Inserting => "inserting",
            State::Yielded => "yielded",
        }
    }

    /// The note, unless it is only the "loading" progress line.
    pub fn last_problem(&self) -> Option<&str> {
        self.note.as_deref().filter(|note| *note != LOADING_NOTE)
    }
}

#[derive(Debug)]
pub enum Input {
    Event(Event, Source),
    ModelsLoaded(Result<(), String>),
    /// Something to tell the user that is not a state change (an insertion failure).
    Note(String),
    /// A [`Note`](Input::Note) that also plays the alert sound: the microphone heard nothing.
    Alert(String),
    /// The input level of the recording, from the capture's level sink.
    Level(f32),
    /// The current status, for the control socket's `status`.
    Query(Sender<Status>),
    Quit,
}

/// A finished recording on its way to the worker.
struct Dictation {
    samples: Vec<f32>,
    device: Option<String>,
    /// When the release was handled: the start of the latency the journal reports.
    released_at: Instant,
    trigger: Source,
}

enum Job {
    Transcribe(Dictation),
    Insert { text: String, delivery: Delivery },
}

/// Where a dictation that produced no text, or failed, is kept, so a lost
/// dictation can be replayed by the bench instead of being gone.
pub struct LostClips {
    pub directory: Option<PathBuf>,
}

pub struct Controller {
    pub inputs: Sender<Input>,
    controller_thread: JoinHandle<()>,
    worker_thread: JoinHandle<()>,
}

impl Controller {
    /// Starts both threads. `make_capture` runs on the controller thread
    /// (an audio stream may not be movable between threads); `load_pipeline`
    /// runs first on the worker thread, so a dictation made while the models
    /// load simply waits for them.
    pub fn start<C, I, F>(
        make_capture: impl FnOnce() -> C + Send + 'static,
        load_pipeline: impl FnOnce() -> Result<Pipeline, whispy_core::Error> + Send + 'static,
        inserter: I,
        lost_clips: LostClips,
        journal: Journal,
        feedback: F,
        show: impl Fn(&Status) + Send + 'static,
    ) -> Controller
    where
        C: Capture + 'static,
        I: Inserter + 'static,
        F: Feedback + 'static,
    {
        let (inputs, receiver) = mpsc::channel();
        let (jobs, worker_thread) =
            spawn_worker(load_pipeline, inserter, lost_clips, journal, inputs.clone());
        let own_inputs = inputs.clone();
        let controller_thread = thread::Builder::new()
            .name("whispy2-controller".into())
            .spawn(move || run(make_capture(), receiver, own_inputs, jobs, feedback, show))
            .expect("the controller thread could not be started");
        Controller {
            inputs,
            controller_thread,
            worker_thread,
        }
    }

    /// Sends an event as if the Fn key had produced it.
    pub fn send(&self, event: Event) {
        self.send_from(event, Source::Fn);
    }

    pub fn send_from(&self, event: Event, source: Source) {
        // The controller only stops on Quit; a send after that has nowhere to go.
        let _ = self.inputs.send(Input::Event(event, source));
    }

    /// Stops both threads and frees the models. Must run before the process
    /// exits: whisper.cpp's Metal device aborts the process when it is torn
    /// down by `exit` with a model still loaded.
    pub fn stop(self) {
        let _ = self.inputs.send(Input::Quit);
        let _ = self.controller_thread.join();
        // The controller thread held the only job sender: the worker's queue
        // is now closed, it finishes its current job and drops the pipeline.
        let _ = self.worker_thread.join();
    }
}

pub const LOADING_NOTE: &str = "Loading the models…";

fn run(
    mut capture: impl Capture,
    receiver: Receiver<Input>,
    own_inputs: Sender<Input>,
    jobs: Sender<Job>,
    mut feedback: impl Feedback,
    show: impl Fn(&Status),
) {
    capture.set_level_sink(Arc::new(move |level| {
        let _ = own_inputs.send(Input::Level(level));
    }));
    let mut machine = Machine::new();
    let mut status = Status {
        state: machine.state(),
        note: Some(LOADING_NOTE.into()),
        models_loaded: false,
    };
    let mut trigger = Source::Fn;
    let mut phase = Phase::Hidden;
    show(&status);
    while let Ok(input) = receiver.recv() {
        let mut models_loaded = status.models_loaded;
        let note = match input {
            Input::Quit => return,
            // Clears the loading note only: a problem reported meanwhile
            // (Input Monitoring missing) must stay on screen.
            Input::ModelsLoaded(Ok(())) => {
                models_loaded = true;
                (status.note.as_deref() == Some(LOADING_NOTE)).then_some(None)
            }
            Input::ModelsLoaded(Err(error)) | Input::Note(error) => Some(Some(error)),
            Input::Alert(note) => {
                feedback.alert();
                Some(Some(note))
            }
            Input::Level(level) => {
                feedback.level(level);
                None
            }
            Input::Query(reply) => {
                let _ = reply.send(status.clone());
                None
            }
            Input::Event(event, source) => {
                let note = note_for(&event);
                if let Some(action) = machine.handle(event) {
                    if action == Action::StartCapture {
                        trigger = source;
                    }
                    if let Err(error) = perform(action, &mut capture, &jobs, trigger) {
                        machine.handle(Event::CaptureFailed);
                        Some(Some(error))
                    } else {
                        note
                    }
                } else {
                    note
                }
            }
        };
        let next_phase = phase_of(machine.state());
        if next_phase != phase {
            phase = next_phase;
            feedback.show(phase);
        }
        let next = Status {
            state: machine.state(),
            note: note.unwrap_or_else(|| status.note.clone()),
            models_loaded,
        };
        if next != status {
            status = next;
            show(&status);
        }
    }
}

/// `Some(new note)` when the event changes what the menu should say beyond the state.
fn note_for(event: &Event) -> Option<Option<String>> {
    match event {
        Event::FnDown(_) => Some(None),
        Event::TranscriptionFailed => Some(Some(
            "The last dictation could not be transcribed; its audio is kept in ~/.whispy/v2-lost/."
                .into(),
        )),
        _ => None,
    }
}

fn perform(
    action: Action,
    capture: &mut impl Capture,
    jobs: &Sender<Job>,
    trigger: Source,
) -> Result<(), String> {
    match action {
        Action::StartCapture => capture
            .start()
            .map_err(|error| format!("The microphone could not be opened: {error}")),
        Action::StopCaptureAndTranscribe => {
            let released_at = Instant::now();
            let samples = capture.stop();
            let _ = jobs.send(Job::Transcribe(Dictation {
                samples,
                device: capture.device_name(),
                released_at,
                trigger,
            }));
            Ok(())
        }
        Action::DiscardCapture => {
            capture.stop();
            Ok(())
        }
        Action::Insert { text, delivery } => {
            let _ = jobs.send(Job::Insert { text, delivery });
            Ok(())
        }
    }
}

/// What the worker keeps of a transcribed dictation until its text is delivered.
struct Pending {
    duration_s: f32,
    released_at: Instant,
    trigger: Source,
    engine: Option<&'static str>,
    length: usize,
}

fn spawn_worker<I: Inserter + 'static>(
    load_pipeline: impl FnOnce() -> Result<Pipeline, whispy_core::Error> + Send + 'static,
    mut inserter: I,
    lost_clips: LostClips,
    journal: Journal,
    controller: Sender<Input>,
) -> (Sender<Job>, JoinHandle<()>) {
    let (jobs, receiver) = mpsc::channel::<Job>();
    let worker_thread = thread::Builder::new()
        .name("whispy2-worker".into())
        .spawn(move || {
            let mut pipeline = match load_pipeline() {
                Ok(pipeline) => {
                    let _ = controller.send(Input::ModelsLoaded(Ok(())));
                    Some(pipeline)
                }
                Err(error) => {
                    let _ = controller.send(Input::ModelsLoaded(Err(format!(
                        "The models could not be loaded: {error}"
                    ))));
                    None
                }
            };
            // One dictation at a time: a Transcribe with text is always followed by its Insert.
            let mut pending: Option<Pending> = None;
            for job in receiver {
                let event = match job {
                    Job::Transcribe(dictation) => {
                        let done = transcribe(pipeline.as_mut(), &dictation, &lost_clips);
                        if let Some(note) = done.alert {
                            let _ = controller.send(Input::Alert(note));
                        }
                        let duration_s = dictation.samples.len() as f32 / SAMPLE_RATE;
                        if matches!(&done.event, Event::Transcribed(text) if !text.trim().is_empty())
                        {
                            pending = Some(Pending {
                                duration_s,
                                released_at: dictation.released_at,
                                trigger: dictation.trigger,
                                engine: done.engine,
                                length: done.length,
                            });
                        } else {
                            journal.record(&Entry {
                                time: log::unix_now(),
                                duration_s,
                                latency_s: dictation.released_at.elapsed().as_secs_f32(),
                                trigger: dictation.trigger,
                                outcome: done.outcome,
                                engine: done.engine.map(str::to_string),
                                length: done.length,
                            });
                        }
                        done.event
                    }
                    Job::Insert { text, delivery } => {
                        let delivered = inserter.deliver(&text, delivery);
                        let outcome = match (&delivered, delivery) {
                            (Err(_), _) => Outcome::Failed,
                            (Ok(()), Delivery::Paste) => Outcome::Inserted,
                            (Ok(()), Delivery::Clipboard) => Outcome::Clipboard,
                        };
                        if let Err(error) = delivered {
                            log::line(&format!("insertion failed: {error}"));
                            let _ = controller.send(Input::Note(error));
                        }
                        if let Some(done) = pending.take() {
                            journal.record(&Entry {
                                time: log::unix_now(),
                                duration_s: done.duration_s,
                                latency_s: done.released_at.elapsed().as_secs_f32(),
                                trigger: done.trigger,
                                outcome,
                                engine: done.engine.map(str::to_string),
                                length: done.length,
                            });
                        }
                        Event::Inserted
                    }
                };
                // After Quit nobody listens; keep draining until the queue closes.
                let _ = controller.send(Input::Event(event, Source::Fn));
            }
        })
        .expect("the worker thread could not be started");
    (jobs, worker_thread)
}

const SAMPLE_RATE: f32 = 16_000.0;

/// A recording at least this long should not be silent (V1's `MIN_SECONDS`
/// for its deaf-take check): shorter ones are taps and accidental presses.
pub const HEARD_NOTHING_MIN_SECONDS: f32 = 0.5;
/// V1's noise floor, on V1's scale: a capture block's RMS times ten
/// (`NOISE_FLOOR_PEAK_LEVEL` in `src/whispy/core/audio.py`), not a sample peak.
/// V1 measured deaf takes between 0.008 and 0.055 and speech from 0.2 up, and
/// raised the line from 0.05 to 0.1 after a 72 s deaf take at 0.055. Read as a
/// sample peak, 0.1 called quiet but real speech silence (2026-11-04).
pub const NOISE_FLOOR: f32 = 0.1;
/// V1's level is a block RMS times this.
const LEVEL_SCALE: f32 = 10.0;
/// The window the level is measured on: 30 ms, no longer than V1's capture
/// blocks, so a short word reads at least as loud as it did in V1.
const LEVEL_WINDOW: usize = 480;

/// Whether the microphone delivered nothing usable: long enough to be a
/// dictation, yet no 30 ms window ever reached the noise floor.
pub fn is_deaf_take(samples: &[f32]) -> bool {
    let seconds = samples.len() as f32 / SAMPLE_RATE;
    let peak_level = samples
        .chunks(LEVEL_WINDOW)
        .map(|window| {
            let mean_square =
                window.iter().map(|sample| sample * sample).sum::<f32>() / window.len() as f32;
            mean_square.sqrt() * LEVEL_SCALE
        })
        .fold(0.0f32, f32::max);
    seconds >= HEARD_NOTHING_MIN_SECONDS && peak_level < NOISE_FLOOR
}

pub fn heard_nothing_note(device: Option<&str>) -> String {
    match device {
        Some(name) => format!("Microphone heard nothing ({name})"),
        None => "Microphone heard nothing".into(),
    }
}

struct Transcribed {
    event: Event,
    /// The outcome when no text is delivered; a delivered text overrides it.
    outcome: Outcome,
    engine: Option<&'static str>,
    length: usize,
    /// Set when the user should hear an alert and see this note.
    alert: Option<String>,
}

impl Transcribed {
    fn without_text(event: Event, outcome: Outcome) -> Self {
        Transcribed {
            event,
            outcome,
            engine: None,
            length: 0,
            alert: None,
        }
    }
}

fn transcribe(
    pipeline: Option<&mut Pipeline>,
    dictation: &Dictation,
    lost_clips: &LostClips,
) -> Transcribed {
    let samples = &dictation.samples;
    // Before any engine: a deaf microphone is not lost speech, and running a
    // model on silence is the false-text risk the gates exist to avoid.
    if is_deaf_take(samples) {
        let mut done =
            Transcribed::without_text(Event::Transcribed(String::new()), Outcome::HeardNothing);
        done.alert = Some(heard_nothing_note(dictation.device.as_deref()));
        return done;
    }
    let Some(pipeline) = pipeline else {
        keep_lost_clip(samples, lost_clips);
        return Transcribed::without_text(Event::TranscriptionFailed, Outcome::Failed);
    };
    match pipeline.transcribe(samples) {
        Ok(transcript) => {
            // Empty text over audio the gates call speech is lost speech: keep it.
            let outcome =
                if transcript.text.is_empty() && Strategy::Gated.prepare(samples).is_some() {
                    keep_lost_clip(samples, lost_clips);
                    Outcome::Lost
                } else if transcript.text.trim().is_empty() {
                    Outcome::Empty
                } else {
                    Outcome::Inserted
                };
            Transcribed {
                length: transcript.text.chars().count(),
                engine: transcript.engine,
                event: Event::Transcribed(transcript.text),
                outcome,
                alert: None,
            }
        }
        Err(error) => {
            log::line(&format!("transcription failed: {error}"));
            keep_lost_clip(samples, lost_clips);
            Transcribed::without_text(Event::TranscriptionFailed, Outcome::Failed)
        }
    }
}

fn keep_lost_clip(samples: &[f32], lost_clips: &LostClips) {
    let Some(directory) = &lost_clips.directory else {
        return;
    };
    if samples.is_empty() {
        return;
    }
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_millis())
        .unwrap_or_default();
    let path = directory.join(format!("lost-{stamp}.wav"));
    let written = std::fs::create_dir_all(directory)
        .map_err(whispy_core::Error::from)
        .and_then(|()| whispy_core::audio::write_wav(&path, samples));
    if let Err(error) = written {
        log::line(&format!(
            "could not keep the lost clip at {}: {error}",
            path.display()
        ));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::log::testing::temp_dir;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Mutex;
    use std::time::Duration;
    use whispy_core::Transcriber;

    struct Echo;
    impl Transcriber for Echo {
        fn name(&self) -> &'static str {
            "echo"
        }
        fn transcribe(&mut self, samples: &[f32]) -> Result<String, whispy_core::Error> {
            Ok(format!("{} samples", samples.len()))
        }
    }

    /// Counts its calls and says a fixed text.
    struct Counting(Arc<AtomicUsize>, &'static str);
    impl Transcriber for Counting {
        fn name(&self) -> &'static str {
            "counting"
        }
        fn transcribe(&mut self, _samples: &[f32]) -> Result<String, whispy_core::Error> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(self.1.to_string())
        }
    }

    struct Clip(Vec<f32>);
    impl Capture for Clip {
        fn start(&mut self) -> Result<(), String> {
            Ok(())
        }
        fn stop(&mut self) -> Vec<f32> {
            self.0.clone()
        }
        fn device_name(&self) -> Option<String> {
            Some("MacBook Pro Microphone".into())
        }
    }

    /// One second of a tone that peaks at `peak`.
    fn tone(seconds: f32, peak: f32) -> Vec<f32> {
        (0..(seconds * 16_000.0) as usize)
            .map(|index| if index % 2 == 0 { peak } else { -peak })
            .collect()
    }

    struct Recorder(Sender<(String, Delivery)>);
    impl Inserter for Recorder {
        fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String> {
            let _ = self.0.send((text.to_string(), delivery));
            Ok(())
        }
    }

    #[derive(Debug, Clone, PartialEq)]
    enum Cue {
        Show(Phase),
        Alert,
    }

    /// Records what the user would see and hear.
    struct Cues(Arc<Mutex<Vec<Cue>>>);
    impl Feedback for Cues {
        fn show(&mut self, phase: Phase) {
            self.0.lock().unwrap().push(Cue::Show(phase));
        }
        fn level(&mut self, _level: f32) {}
        fn alert(&mut self) {
            self.0.lock().unwrap().push(Cue::Alert);
        }
    }

    fn no_journal() -> Journal {
        Journal { directory: None }
    }

    fn pipeline(transcriber: impl Transcriber + 'static) -> Result<Pipeline, whispy_core::Error> {
        Ok(Pipeline::new(Box::new(transcriber), None, Strategy::Raw))
    }

    fn wait_for(what: &str, condition: impl Fn() -> bool) {
        let deadline = Instant::now() + Duration::from_secs(5);
        while !condition() {
            assert!(Instant::now() < deadline, "{what}");
            thread::sleep(Duration::from_millis(5));
        }
    }

    /// Holds Fn for `seconds` of fake time and waits for the machine to finish.
    fn dictate(controller: &Controller, seconds: u64) {
        let start = Instant::now();
        controller.send(Event::FnDown(start));
        controller.send(Event::FnUp(start + Duration::from_secs(seconds)));
    }

    fn journal_lines(directory: &std::path::Path) -> Vec<String> {
        std::fs::read_to_string(directory.join(crate::journal::FILE_NAME))
            .unwrap_or_default()
            .lines()
            .map(str::to_string)
            .collect()
    }

    #[test]
    fn a_held_dictation_reaches_the_inserter_and_the_menu_returns_to_idle() {
        let (delivered, inserted) = mpsc::channel();
        let statuses = Arc::new(Mutex::new(Vec::new()));
        let seen = Arc::clone(&statuses);
        let controller = Controller::start(
            || Clip(tone(1.0, 0.5)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            crate::feedback::NoFeedback,
            move |status: &Status| seen.lock().unwrap().push(status.state),
        );
        dictate(&controller, 1);
        let (text, delivery) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(text, "16000 samples");
        assert_eq!(delivery, Delivery::Paste);
        // The worker reports the insertion after delivering it: wait for idle.
        wait_for("never back to idle", || {
            statuses.lock().unwrap().last() == Some(&State::Idle)
        });
        controller.stop();
        assert!(statuses.lock().unwrap().contains(&State::Inserting));
    }

    #[test]
    fn a_problem_reported_while_loading_outlives_the_loading_note() {
        let (delivered, _inserted) = mpsc::channel();
        let (statuses, shown) = mpsc::channel();
        let (release_loading, loading_released) = mpsc::channel::<()>();
        let controller = Controller::start(
            || Clip(Vec::new()),
            move || {
                let _ = loading_released.recv();
                pipeline(Echo)
            },
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            crate::feedback::NoFeedback,
            move |status: &Status| {
                let _ = statuses.send(status.clone());
            },
        );
        let problem = "Fn is not available".to_string();
        let _ = controller.inputs.send(Input::Note(problem.clone()));
        release_loading.send(()).unwrap();
        // The models-loaded report arrives right after; give it time to be handled.
        thread::sleep(Duration::from_millis(200));
        controller.stop();
        let last = shown.try_iter().last().unwrap();
        assert_eq!(last.note, Some(problem));
    }

    #[test]
    fn a_microphone_failure_is_shown_and_does_not_strand_the_machine() {
        struct Broken;
        impl Capture for Broken {
            fn start(&mut self) -> Result<(), String> {
                Err("no input device".into())
            }
            fn stop(&mut self) -> Vec<f32> {
                Vec::new()
            }
        }
        let (delivered, _inserted) = mpsc::channel();
        let (statuses, shown) = mpsc::channel();
        let controller = Controller::start(
            || Broken,
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            crate::feedback::NoFeedback,
            move |status: &Status| {
                let _ = statuses.send(status.clone());
            },
        );
        controller.send(Event::FnDown(Instant::now()));
        let failure = shown
            .iter()
            .find(|status: &Status| {
                status
                    .note
                    .as_deref()
                    .is_some_and(|note| note.contains("no input device"))
            })
            .unwrap();
        assert_eq!(failure.state, State::Idle);
        controller.stop();
    }

    #[test]
    fn a_three_second_deaf_take_is_reported_without_calling_an_engine() {
        let (delivered, inserted) = mpsc::channel();
        let calls = Arc::new(AtomicUsize::new(0));
        let engine_calls = Arc::clone(&calls);
        let lost = temp_dir("controller-deaf");
        let (statuses, shown) = mpsc::channel();
        let cues = Arc::new(Mutex::new(Vec::new()));
        let controller = Controller::start(
            || Clip(tone(3.0, 0.006)),
            move || pipeline(Counting(engine_calls, "hello")),
            Recorder(delivered),
            LostClips {
                directory: Some(lost.clone()),
            },
            no_journal(),
            Cues(Arc::clone(&cues)),
            move |status: &Status| {
                let _ = statuses.send(status.clone());
            },
        );
        dictate(&controller, 3);
        let reported = shown
            .iter()
            .find(|status: &Status| {
                status
                    .note
                    .as_deref()
                    .is_some_and(|n| n.contains("heard nothing"))
            })
            .unwrap();
        assert_eq!(
            reported.note.as_deref(),
            Some("Microphone heard nothing (MacBook Pro Microphone)")
        );
        controller.stop();
        assert_eq!(calls.load(Ordering::SeqCst), 0, "no engine call");
        assert!(inserted.try_recv().is_err(), "nothing inserted");
        assert_eq!(std::fs::read_dir(&lost).unwrap().count(), 0, "no lost clip");
        // The panel went up and down, and the alert sounded.
        let cues = cues.lock().unwrap();
        assert!(cues.contains(&Cue::Alert));
    }

    #[test]
    fn a_short_silent_tap_is_not_a_deaf_take() {
        assert!(!is_deaf_take(&tone(0.3, 0.0)));
        assert!(!is_deaf_take(&tone(0.49, 0.0)));
        assert!(is_deaf_take(&tone(0.5, 0.0099)));
        assert!(!is_deaf_take(&tone(3.0, 0.01)));
        // Quiet real speech: sample peaks under 0.1, level well above the floor.
        assert!(!is_deaf_take(&tone(3.0, 0.05)));
        assert_eq!(heard_nothing_note(None), "Microphone heard nothing");
        // Through the controller: nothing is reported for 0.3 s of silence.
        let (delivered, _inserted) = mpsc::channel();
        let cues = Arc::new(Mutex::new(Vec::new()));
        let (statuses, shown) = mpsc::channel();
        let controller = Controller::start(
            || Clip(tone(0.3, 0.0)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            Cues(Arc::clone(&cues)),
            move |status: &Status| {
                let _ = statuses.send(status.clone());
            },
        );
        dictate(&controller, 1);
        controller.stop();
        assert!(!cues.lock().unwrap().contains(&Cue::Alert));
        assert!(shown
            .try_iter()
            .all(|status| !status.note.unwrap_or_default().contains("heard nothing")));
    }

    #[test]
    fn the_indicator_follows_the_dictation_and_alerts_on_heard_nothing() {
        let (delivered, inserted) = mpsc::channel();
        let cues = Arc::new(Mutex::new(Vec::new()));
        let seen = Arc::clone(&cues);
        let controller = Controller::start(
            || Clip(tone(1.0, 0.5)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            Cues(seen),
            |_: &Status| {},
        );
        dictate(&controller, 1);
        inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        wait_for("the panel never hid", || {
            cues.lock().unwrap().last() == Some(&Cue::Show(Phase::Hidden))
        });
        controller.stop();
        assert_eq!(
            *cues.lock().unwrap(),
            vec![
                Cue::Show(Phase::Recording),
                Cue::Show(Phase::Transcribing),
                Cue::Show(Phase::Hidden)
            ]
        );

        let heard_cues = Arc::new(Mutex::new(Vec::new()));
        let (delivered, _inserted) = mpsc::channel();
        let controller = Controller::start(
            || Clip(tone(2.0, 0.001)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            Cues(Arc::clone(&heard_cues)),
            |_: &Status| {},
        );
        dictate(&controller, 2);
        wait_for("no alert", || {
            heard_cues.lock().unwrap().contains(&Cue::Alert)
        });
        controller.stop();
    }

    #[test]
    fn an_inserted_dictation_leaves_a_journal_line_without_its_text() {
        let (delivered, inserted) = mpsc::channel();
        let directory = temp_dir("controller-journal");
        let controller = Controller::start(
            || Clip(tone(4.0, 0.5)),
            || {
                pipeline(Counting(
                    Arc::new(AtomicUsize::new(0)),
                    "mot de passe secret",
                ))
            },
            Recorder(delivered),
            LostClips { directory: None },
            Journal {
                directory: Some(directory.clone()),
            },
            crate::feedback::NoFeedback,
            |_: &Status| {},
        );
        controller.send_from(Event::FnDown(Instant::now()), Source::Socket);
        controller.send_from(
            Event::FnUp(Instant::now() + Duration::from_secs(4)),
            Source::Socket,
        );
        inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        wait_for("no journal line", || !journal_lines(&directory).is_empty());
        controller.stop();
        let lines = journal_lines(&directory);
        assert_eq!(lines.len(), 1, "{lines:?}");
        let line = &lines[0];
        assert!(line.contains("\"outcome\":\"inserted\""), "{line}");
        assert!(line.contains("\"trigger\":\"socket\""), "{line}");
        assert!(
            line.contains("\"engine\":null") || line.contains("\"engine\":\""),
            "{line}"
        );
        assert!(line.contains("\"length\":19"), "{line}");
        assert!(line.contains("\"duration_s\":4.000"), "{line}");
        assert!(line.contains("\"latency_s\":"), "{line}");
        assert!(!line.contains("secret"), "the text must never be journaled");
    }

    #[test]
    fn an_unwritable_journal_does_not_stop_the_delivery() {
        let (delivered, inserted) = mpsc::channel();
        let blocker = temp_dir("controller-blocked").join("file");
        std::fs::write(&blocker, "").unwrap();
        let controller = Controller::start(
            || Clip(tone(1.0, 0.5)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            // The "directory" is a file: creating the journal fails.
            Journal {
                directory: Some(blocker.join("v2")),
            },
            crate::feedback::NoFeedback,
            |_: &Status| {},
        );
        dictate(&controller, 1);
        let (text, _) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(text, "16000 samples");
        controller.stop();
    }

    #[test]
    fn a_heard_nothing_dictation_is_journaled_as_such() {
        let (delivered, _inserted) = mpsc::channel();
        let directory = temp_dir("controller-journal-deaf");
        let cues = Arc::new(Mutex::new(Vec::new()));
        let controller = Controller::start(
            || Clip(tone(3.0, 0.006)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            Journal {
                directory: Some(directory.clone()),
            },
            Cues(Arc::clone(&cues)),
            |_: &Status| {},
        );
        dictate(&controller, 3);
        wait_for("no journal line", || !journal_lines(&directory).is_empty());
        controller.stop();
        let lines = journal_lines(&directory);
        assert!(
            lines[0].contains("\"outcome\":\"heard_nothing\""),
            "{lines:?}"
        );
        assert!(lines[0].contains("\"engine\":null"));
        assert!(lines[0].contains("\"trigger\":\"fn\""));
    }

    #[test]
    fn a_status_query_answers_with_the_state_and_models() {
        let (delivered, _inserted) = mpsc::channel();
        let controller = Controller::start(
            || Clip(Vec::new()),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            crate::feedback::NoFeedback,
            |_: &Status| {},
        );
        let asked = |controller: &Controller| {
            let (reply, answer) = mpsc::channel();
            controller.inputs.send(Input::Query(reply)).unwrap();
            answer.recv_timeout(Duration::from_secs(2)).unwrap()
        };
        wait_for("models never loaded", || asked(&controller).models_loaded);
        let status = asked(&controller);
        assert_eq!(status.state_name(), "idle");
        assert_eq!(status.last_problem(), None);
        controller.stop();
    }

    #[test]
    fn a_socket_start_then_stop_dictates_and_yielding_refuses_a_start() {
        use crate::control::{dispatch, Request};
        let (delivered, inserted) = mpsc::channel();
        let controller = Controller::start(
            || Clip(tone(2.0, 0.5)),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            crate::feedback::NoFeedback,
            |_: &Status| {},
        );
        assert_eq!(dispatch(&controller.inputs, Request::Start), "ok");
        // Immediately: still a hold, not a tap.
        assert_eq!(dispatch(&controller.inputs, Request::Stop), "ok");
        let (text, _) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(text, "32000 samples");
        wait_for("never idle", || {
            dispatch(&controller.inputs, Request::Status).contains("\"state\":\"idle\"")
        });
        assert!(dispatch(&controller.inputs, Request::Status).contains("\"models_loaded\":true"));
        // A stop while idle changes nothing.
        assert_eq!(dispatch(&controller.inputs, Request::Stop), "ok");
        assert!(dispatch(&controller.inputs, Request::Status).contains("\"state\":\"idle\""));

        controller.send(Event::V1Running(true));
        wait_for("never yielded", || {
            dispatch(&controller.inputs, Request::Status).contains("\"yielded\":true")
        });
        for request in [Request::Start, Request::Toggle] {
            assert!(dispatch(&controller.inputs, request).contains("V1 is running"));
        }
        assert!(dispatch(&controller.inputs, Request::Status).contains("\"state\":\"yielded\""));
        controller.stop();
    }
}

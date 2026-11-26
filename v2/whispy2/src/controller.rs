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
//!
//! « Type while speaking » (toggle mode, V1's `type_while_speaking`): while the
//! dictation records, the controller drains the microphone at each level beat
//! and queues the audio; the worker keeps a rolling [`Streamer`] that
//! re-transcribes the open sentence about every 0.6 s and types a sentence once
//! two passes agree on it. After each pass the worker sends the pill the words
//! heard so far ([`Input::Caption`]). The stopping press queues the rest of the
//! audio, which goes through the full pipeline; its text goes back through the
//! machine like any dictation's. One queue, one worker: audio and passes are
//! handled in recording order and never two at once; a job queued behind audio
//! (the stop) is never kept waiting by a pass it did not need.

use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use whispy_core::stream::{PassStats, Streamer};
use whispy_core::{Pipeline, Strategy};

use crate::feedback::{phase_of, Caption, Feedback, Phase};
use crate::journal::{Entry, Journal, Outcome};
use crate::log;
use crate::machine::{Action, Delivery, Event, Machine, Mode, State, RECORDING_LIMIT};
use crate::menu_model::{Alert, Pane};
use crate::settings::TriggerMode;

/// Where the audio-level updates of a recording go (see [`Capture::set_level_sink`]).
pub type LevelSink = Arc<dyn Fn(f32) + Send + Sync>;

/// The microphone, as the controller sees it: 16 kHz mono out.
pub trait Capture {
    fn start(&mut self) -> Result<(), String>;
    /// Stops the recording and returns what was recorded since the last
    /// [`take_recorded`](Capture::take_recorded) (all of it when there was none),
    /// 16 kHz mono `f32`.
    fn stop(&mut self) -> Vec<f32>;
    /// What was recorded since the last take, 16 kHz mono `f32`; the recording
    /// goes on. A capture that cannot hand out a recording in progress returns
    /// nothing, and everything comes at the stop.
    fn take_recorded(&mut self) -> Vec<f32> {
        Vec::new()
    }
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

/// What triggered an edge: the trigger key (Fn by default) or the control socket. Only the
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
    /// How the trigger key works right now (a change applies at the next rest).
    pub trigger_mode: TriggerMode,
    /// The System Settings pane of the last permission alert, if any: the menu
    /// shows « Missing permission… » and opens it.
    pub permission_pane: Option<Pane>,
}

impl Status {
    pub fn headline(&self) -> &'static str {
        match self.state {
            State::Idle => match self.trigger_mode {
                TriggerMode::Hold => "Ready — hold the trigger key to dictate",
                TriggerMode::Toggle => "Ready — press the trigger key to start dictating",
            },
            State::Recording {
                mode: Mode::Hold, ..
            } => "Recording — release the trigger key to insert",
            State::Recording {
                mode: Mode::Toggle, ..
            } => "Recording — press the trigger key to stop",
            State::Transcribing { .. } => "Transcribing…",
            State::Inserting => "Inserting…",
            State::Yielded => "Whispy V1 is running — the trigger key is left to it",
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

/// What the control socket reads besides the [`Status`]. Kept out of it on
/// purpose: the status is shown (and logged) at each change, and the level
/// changes twenty times a second.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Live {
    /// The input level of the recording, 0 when nothing records.
    pub level: f32,
    /// The whole text of the last dictation since V2 started; never on disk.
    pub last_text: Option<String>,
}

#[derive(Debug)]
pub enum Input {
    Event(Event, Source),
    ModelsLoaded(Result<(), String>),
    /// Something to tell the user that is not a state change (an insertion failure).
    Note(String),
    /// A [`Note`](Input::Note) that is also one of V1's notifications (see [`Alert`]).
    Alert(Alert),
    /// The input level of the recording, from the capture's level sink. Also the
    /// beat at which a recording is drained and cut.
    Level(f32),
    /// The words a dictation has heard so far, from the worker after each rolling
    /// pass. Shown only while recording.
    Caption(Caption),
    /// V1's `type_while_speaking`: in toggle mode, type each piece as soon as it
    /// is transcribed. Applies from the next dictation.
    TypeWhileSpeaking(bool),
    /// The current status, for the control socket's `status`.
    Query(Sender<Status>),
    /// The whole text of a dictation, from the worker once it is transcribed
    /// (delivered or not). Kept in memory only, for the socket's `last`.
    Dictated(String),
    /// What the socket shows besides the status: the level and the last text.
    Live(Sender<Live>),
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
    /// A dictation begins: a fresh [`Streamer`], which captions every dictation
    /// and, with `types_live`, also types it while it is spoken.
    StartStream {
        types_live: bool,
    },
    /// More audio of the dictation being heard.
    StreamAudio(Vec<f32>),
    /// The end of a dictation: typed live, the open sentence goes through the
    /// full pipeline; otherwise the whole recording is transcribed as one block.
    /// Either way its text goes back through the machine.
    FinishStream {
        dictation: Dictation,
        delivery: Delivery,
    },
    /// The dictation was cancelled: forget it.
    DiscardStream,
    Insert {
        text: String,
        delivery: Delivery,
    },
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

/// The worker's loader: the models a fresh install lacks are downloaded first
/// (`announce` tells the user, it takes minutes), then the pipeline is loaded.
pub fn load_models(announce: impl Fn(&Alert)) -> Result<Pipeline, whispy_core::Error> {
    let downloads = whispy_core::models::missing_downloads();
    if !downloads.is_empty() {
        let megabytes = downloads.iter().map(|d| d.bytes).sum::<u64>() / 1_000_000;
        log::line(&format!(
            "downloading {} model file(s), {megabytes} MB",
            downloads.len()
        ));
        announce(&Alert::downloading_models(megabytes));
        whispy_core::models::download_missing()?;
        log::line("models downloaded");
    }
    Pipeline::load_default()
}

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
    let mut recorder = Recorder {
        capture,
        is_recording: false,
        trigger: Source::Fn,
        is_typing_while_speaking: crate::settings::Settings::default().type_while_speaking,
    };
    let mut status = Status {
        state: machine.state(),
        note: Some(LOADING_NOTE.into()),
        models_loaded: false,
        trigger_mode: machine.trigger_mode(),
        permission_pane: None,
    };
    let mut is_load_failed = false;
    let mut permission_pane: Option<Pane> = None;
    let mut phase = Phase::Hidden;
    let mut live = Live::default();
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
            Input::ModelsLoaded(Err(error)) => {
                is_load_failed = true;
                let alert = Alert::model_failed(&error);
                let note = alert.message.clone();
                raise(&mut feedback, &mut permission_pane, alert);
                Some(Some(note))
            }
            Input::Note(error) => Some(Some(error)),
            Input::Alert(alert) => {
                let note = alert.message.clone();
                raise(&mut feedback, &mut permission_pane, alert);
                Some(Some(note))
            }
            Input::Level(level) => {
                feedback.level(level);
                if phase == Phase::Recording {
                    live.level = level;
                }
                recorder.send_audio(&jobs);
                None
            }
            // A caption that arrives after the stop is late: the pill is gone.
            Input::Caption(caption) => {
                if phase == Phase::Recording {
                    feedback.caption(&caption);
                }
                None
            }
            Input::TypeWhileSpeaking(is_on) => {
                recorder.is_typing_while_speaking = is_on;
                None
            }
            Input::Query(reply) => {
                let _ = reply.send(status.clone());
                None
            }
            Input::Dictated(text) => {
                live.last_text = Some(text);
                None
            }
            Input::Live(reply) => {
                let _ = reply.send(live.clone());
                None
            }
            Input::Event(event, source) => {
                let note = note_for(&event);
                let is_tick = matches!(event, Event::Tick(_));
                if let Some(action) = machine.handle(event) {
                    if action == Action::StartCapture {
                        recorder.trigger = source;
                    }
                    let alert = alert_for(&action, is_tick, models_loaded, is_load_failed);
                    if let Err(error) = recorder.perform(action, machine.state(), &jobs) {
                        machine.handle(Event::CaptureFailed);
                        raise(
                            &mut feedback,
                            &mut permission_pane,
                            Alert::no_microphone(&error),
                        );
                        Some(Some(error))
                    } else if let Some(alert) = alert {
                        let note = alert.message.clone();
                        raise(&mut feedback, &mut permission_pane, alert);
                        Some(Some(note))
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
            live.level = 0.0;
            feedback.show(phase);
        }
        let next = Status {
            state: machine.state(),
            note: note.unwrap_or_else(|| status.note.clone()),
            models_loaded,
            trigger_mode: machine.trigger_mode(),
            permission_pane,
        };
        if next != status {
            status = next;
            show(&status);
        }
    }
}

/// Sends `alert` to the user and remembers its permission pane for the menu.
fn raise(feedback: &mut impl Feedback, permission_pane: &mut Option<Pane>, alert: Alert) {
    if alert.pane.is_some() {
        *permission_pane = alert.pane;
    }
    feedback.alert(alert);
}

/// The V1 alert an action carries, if any: a watchdog stop (the Tick that
/// ended the recording), or a dictation that ended while the models were
/// still loading (V1's `_on_recording_stop`).
fn alert_for(
    action: &Action,
    is_tick: bool,
    models_loaded: bool,
    is_load_failed: bool,
) -> Option<Alert> {
    if *action != Action::StopCaptureAndTranscribe {
        return None;
    }
    if is_tick {
        return Some(Alert::dictation_stopped(&format!(
            "Dictation stopped after {} minutes. Any transcribed text was copied to the clipboard.",
            RECORDING_LIMIT.as_secs() / 60
        )));
    }
    (!models_loaded && !is_load_failed).then(Alert::model_still_loading)
}

/// The alert an insertion failure is, if it is V1's « Can't type into apps »:
/// the inserter's message names Accessibility when macOS refused the keystrokes.
pub fn insertion_alert(error: &str) -> Option<Alert> {
    error
        .contains("Accessibility")
        .then(|| Alert::cannot_type(error))
}

/// `Some(new note)` when the event changes what the menu should say beyond the state.
fn note_for(event: &Event) -> Option<Option<String>> {
    match event {
        Event::TriggerDown(_) => Some(None),
        Event::TranscriptionFailed => Some(Some(
            "The last dictation could not be transcribed; its audio is kept in ~/.whispy/v2-lost/."
                .into(),
        )),
        _ => None,
    }
}

/// The controller's side of a recording: the microphone and the audio it hands,
/// beat by beat, to the worker's streamer (which captions every dictation).
struct Recorder<C: Capture> {
    capture: C,
    is_recording: bool,
    /// What started the current recording, for the journal.
    trigger: Source,
    is_typing_while_speaking: bool,
}

impl<C: Capture> Recorder<C> {
    /// Runs `action`; `state` is the machine's state right after deciding it.
    fn perform(&mut self, action: Action, state: State, jobs: &Sender<Job>) -> Result<(), String> {
        match action {
            Action::StartCapture => {
                self.is_recording = false;
                self.capture
                    .start()
                    .map_err(|error| format!("The microphone could not be opened: {error}"))?;
                // Every dictation is captioned; only one in toggle mode with the
                // setting on is also typed live. Decided once, at the start: a
                // setting flipped mid-dictation must not leave half of it typed
                // live and the rest at the stop. Hold mode never types live: the
                // trigger is held down meanwhile.
                let is_toggle = matches!(
                    state,
                    State::Recording {
                        mode: Mode::Toggle,
                        ..
                    }
                );
                self.is_recording = true;
                let _ = jobs.send(Job::StartStream {
                    types_live: is_toggle && self.is_typing_while_speaking,
                });
                Ok(())
            }
            Action::StopCaptureAndTranscribe => {
                let released_at = Instant::now();
                let rest = self.capture.stop();
                let delivery = match state {
                    State::Transcribing { delivery } => delivery,
                    _ => Delivery::Paste,
                };
                let dictation = Dictation {
                    samples: rest,
                    device: self.capture.device_name(),
                    released_at,
                    trigger: self.trigger,
                };
                self.is_recording = false;
                let _ = jobs.send(Job::FinishStream {
                    dictation,
                    delivery,
                });
                Ok(())
            }
            Action::DiscardCapture => {
                self.capture.stop();
                if std::mem::take(&mut self.is_recording) {
                    let _ = jobs.send(Job::DiscardStream);
                }
                Ok(())
            }
            Action::Insert { text, delivery } => {
                let _ = jobs.send(Job::Insert { text, delivery });
                Ok(())
            }
        }
    }

    /// While recording: drains the microphone and queues the audio for the
    /// worker's streamer.
    fn send_audio(&mut self, jobs: &Sender<Job>) {
        if !self.is_recording {
            return;
        }
        let samples = self.capture.take_recorded();
        if !samples.is_empty() {
            let _ = jobs.send(Job::StreamAudio(samples));
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
            // The dictation being heard, from its first audio to its stop.
            let mut live = LiveDictation::default();
            // A job met while draining the audio queue: handled before blocking again.
            let mut held: Option<Job> = None;
            loop {
                let job = match held.take() {
                    Some(job) => job,
                    None => match receiver.recv() {
                        Ok(job) => job,
                        Err(_) => break,
                    },
                };
                let (done, dictation, duration_s) = match job {
                    Job::StartStream { types_live } => {
                        live = LiveDictation::started(types_live);
                        continue;
                    }
                    Job::StreamAudio(samples) => {
                        live.push(&samples);
                        // Whatever is queued already: more audio joins this one,
                        // anything else (the stop) is not kept waiting behind a pass.
                        while held.is_none() {
                            match receiver.try_recv() {
                                Ok(Job::StreamAudio(more)) => live.push(&more),
                                Ok(other) => held = Some(other),
                                Err(_) => break,
                            }
                        }
                        if held.is_none() && live.is_pass_due() {
                            let (failure, caption) = live.pass(pipeline.as_mut(), &mut inserter);
                            if let Some(error) = failure {
                                let _ = controller.send(insertion_input(error));
                            }
                            if let Some(caption) = caption {
                                let _ = controller.send(Input::Caption(caption));
                            }
                        }
                        continue;
                    }
                    Job::DiscardStream => {
                        live = LiveDictation::default();
                        continue;
                    }
                    Job::FinishStream {
                        mut dictation,
                        delivery,
                    } => {
                        let finished = std::mem::take(&mut live);
                        let duration_s =
                            finished.seconds + dictation.samples.len() as f32 / SAMPLE_RATE;
                        let done = if finished.types_live {
                            finished.finish(pipeline.as_mut(), &dictation, delivery, &lost_clips)
                        } else {
                            // Nothing was typed: the whole recording is one block.
                            let mut whole = finished.heard;
                            whole.append(&mut dictation.samples);
                            dictation.samples = whole;
                            transcribe(pipeline.as_mut(), &dictation, &lost_clips)
                        };
                        (done, dictation, duration_s)
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
                            let _ = controller.send(insertion_input(error));
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
                        // After Quit nobody listens; keep draining until the queue closes.
                        let _ = controller.send(Input::Event(Event::Inserted, Source::Fn));
                        continue;
                    }
                };
                if let Some(note) = done.alert {
                    let _ = controller.send(Input::Alert(Alert::microphone_heard_nothing(&note)));
                }
                if !done.whole.trim().is_empty() {
                    let _ = controller.send(Input::Dictated(done.whole.clone()));
                }
                if matches!(&done.event, Event::Transcribed(text) if !text.trim().is_empty()) {
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
                let _ = controller.send(Input::Event(done.event, Source::Fn));
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

/// What an insertion failure tells the controller: V1's alert when it is one, else a note.
fn insertion_input(error: String) -> Input {
    match insertion_alert(&error) {
        Some(alert) => Input::Alert(alert),
        None => Input::Note(error),
    }
}

/// Whether the microphone delivered nothing usable: long enough to be a
/// dictation, yet no 30 ms window ever reached the noise floor.
pub fn is_deaf_take(samples: &[f32]) -> bool {
    is_deaf(samples.len() as f32 / SAMPLE_RATE, peak_level(samples))
}

fn is_deaf(seconds: f32, peak_level: f32) -> bool {
    seconds >= HEARD_NOTHING_MIN_SECONDS && peak_level < NOISE_FLOOR
}

/// The loudest 30 ms window, on V1's level scale.
fn peak_level(samples: &[f32]) -> f32 {
    samples
        .chunks(LEVEL_WINDOW)
        .map(|window| {
            let mean_square =
                window.iter().map(|sample| sample * sample).sum::<f32>() / window.len() as f32;
            mean_square.sqrt() * LEVEL_SCALE
        })
        .fold(0.0f32, f32::max)
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
    /// The whole text of the dictation, typed while spoken or not; empty when none.
    whole: String,
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
            whole: String::new(),
            alert: None,
        }
    }
}

fn transcribe(
    pipeline: Option<&mut Pipeline>,
    dictation: &Dictation,
    lost_clips: &LostClips,
) -> Transcribed {
    // Before any engine: a deaf microphone is not lost speech, and running a
    // model on silence is the false-text risk the gates exist to avoid.
    if is_deaf_take(&dictation.samples) {
        return heard_nothing(dictation);
    }
    transcribe_samples(pipeline, &dictation.samples, lost_clips)
}

fn heard_nothing(dictation: &Dictation) -> Transcribed {
    let mut done =
        Transcribed::without_text(Event::Transcribed(String::new()), Outcome::HeardNothing);
    done.alert = Some(heard_nothing_note(dictation.device.as_deref()));
    done
}

/// The engines on `samples`, with no deaf-take check; a lost text keeps its clip.
/// The stop of a dictation typed while spoken: the streamer hears its open
/// audio once more, in context, and the text comes back already joined to
/// what was typed. A lost text keeps its clip, as [`transcribe_samples`] does.
fn finish_stream(
    pipeline: Option<&mut Pipeline>,
    streamer: Streamer,
    lost_clips: &LostClips,
) -> Transcribed {
    let Some(pipeline) = pipeline else {
        let rest = streamer.rest().to_vec();
        let held = streamer.flush();
        if held.is_empty() {
            return transcribe_samples(None, &rest, lost_clips);
        }
        keep_lost_clip(&rest, lost_clips);
        return held_number(held);
    };
    let rest = streamer.rest().to_vec();
    match streamer.finish(pipeline) {
        Ok(finish) => {
            let outcome = match (&finish.lost, finish.typed.trim().is_empty()) {
                (Some(clip), _) => {
                    keep_lost_clip(clip, lost_clips);
                    Outcome::Lost
                }
                (None, true) => Outcome::Empty,
                (None, false) => Outcome::Inserted,
            };
            Transcribed {
                length: finish.typed.chars().count(),
                engine: finish.engine,
                whole: finish.typed.clone(),
                event: Event::Transcribed(finish.typed),
                outcome,
                alert: None,
            }
        }
        Err(error) => {
            log::line(&format!("transcription failed: {error}"));
            keep_lost_clip(&rest, lost_clips);
            Transcribed::without_text(Event::TranscriptionFailed, Outcome::Failed)
        }
    }
}

/// The stop's outcome when only the text a number was held back with is left.
fn held_number(text: String) -> Transcribed {
    if text.trim().is_empty() {
        return Transcribed::without_text(Event::Transcribed(String::new()), Outcome::Empty);
    }
    Transcribed {
        length: text.chars().count(),
        engine: None,
        whole: text.clone(),
        event: Event::Transcribed(text),
        outcome: Outcome::Inserted,
        alert: None,
    }
}

fn transcribe_samples(
    pipeline: Option<&mut Pipeline>,
    samples: &[f32],
    lost_clips: &LostClips,
) -> Transcribed {
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
                whole: transcript.text.clone(),
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

/// How much of the typed text the pill shows (about one line of it).
const CAPTION_COMMITTED_CHARS: usize = 120;

/// The end of `text`, about `max_chars` long, cut on a char boundary and, when
/// it can be, on a word boundary.
fn caption_tail(text: &str, max_chars: usize) -> String {
    let count = text.chars().count();
    if count <= max_chars {
        return text.to_string();
    }
    let start = text
        .char_indices()
        .nth(count - max_chars)
        .map_or(0, |(index, _)| index);
    let tail = &text[start..];
    let cut_mid_word = text[..start]
        .chars()
        .next_back()
        .is_some_and(|before| !before.is_whitespace())
        && tail
            .chars()
            .next()
            .is_some_and(|first| !first.is_whitespace());
    if cut_mid_word {
        if let Some(space) = tail.find(char::is_whitespace) {
            return tail[space..].trim_start().to_string();
        }
    }
    tail.trim_start().to_string()
}

/// The log line of one rolling pass: counts and times only, never any dictated text.
fn pass_line(stats: &PassStats, types_live: bool) -> String {
    format!(
        "stream pass: live={} window={:.1}s took={:.2}s words={} stable={} committed={} forced={}",
        if types_live { "yes" } else { "no" },
        stats.window_s,
        stats.took_s,
        stats.words,
        stats.stable,
        stats.committed_words,
        if stats.forced { "yes" } else { "no" },
    )
}

/// A dictation being heard, between its first audio and its stop. Lives on the
/// worker thread only: the [`Streamer`] is not `Send`.
#[derive(Default)]
struct LiveDictation {
    /// None until the dictation starts.
    streamer: Option<Streamer>,
    /// Whether the passes' text is typed as it is spoken; otherwise the passes
    /// only feed the caption and the stop transcribes `heard` as one block.
    types_live: bool,
    /// Every sample pushed, kept only when not typing live.
    heard: Vec<f32>,
    /// The text handed to the inserter so far (the text of a pass whose
    /// insertion failed included).
    typed: String,
    /// The audio so far, for the journal and the deaf-take check.
    seconds: f32,
    peak_level: f32,
    engine: Option<&'static str>,
    has_insertion_failed: bool,
    /// The last caption sent to the controller: an unchanged one is not sent again.
    last_caption: Caption,
}

impl LiveDictation {
    fn started(types_live: bool) -> Self {
        LiveDictation {
            streamer: Some(Streamer::new()),
            types_live,
            ..LiveDictation::default()
        }
    }

    fn push(&mut self, samples: &[f32]) {
        self.seconds += samples.len() as f32 / SAMPLE_RATE;
        self.peak_level = self.peak_level.max(peak_level(samples));
        if !self.types_live {
            self.heard.extend_from_slice(samples);
        }
        if let Some(streamer) = self.streamer.as_mut() {
            streamer.push(samples);
        }
    }

    fn is_pass_due(&self) -> bool {
        self.streamer.as_ref().is_some_and(Streamer::is_pass_due)
    }

    /// One rolling pass: types what it committed after the text before it.
    /// Returns the insertion error the user must hear about (the first of the
    /// dictation only) and the caption to show, when it changed. Skipped while
    /// the models are not loaded.
    fn pass(
        &mut self,
        pipeline: Option<&mut Pipeline>,
        inserter: &mut impl Inserter,
    ) -> (Option<String>, Option<Caption>) {
        let (Some(streamer), Some(pipeline)) = (self.streamer.as_mut(), pipeline) else {
            return (None, None);
        };
        let update = match streamer.pass(pipeline) {
            Ok(update) => update,
            Err(error) => {
                log::line(&format!("stream pass failed: {error}"));
                return (None, None);
            }
        };
        log::line(&pass_line(&update.stats, self.types_live));
        let mut failure = None;
        if self.types_live && !update.typed.is_empty() {
            self.typed.push_str(&update.typed);
            self.engine = self.engine.or(Some(pipeline.primary_name()));
            if let Err(error) = inserter.deliver(&update.typed, Delivery::Paste) {
                log::line(&format!("insertion of a passage failed: {error}"));
                if !self.has_insertion_failed {
                    failure = Some(error);
                }
                self.has_insertion_failed = true;
            }
        }
        let caption = Caption {
            committed: caption_tail(streamer.committed(), CAPTION_COMMITTED_CHARS),
            provisional: update.provisional,
        };
        let changed = caption != self.last_caption;
        if changed {
            self.last_caption = caption.clone();
        }
        (failure, changed.then_some(caption))
    }

    /// The stop. The audio the passes left open goes through the full pipeline.
    /// The event carries what the machine inserts: that last text; the whole
    /// dictation when it goes to the clipboard (the watchdog), or when a passage
    /// could not be typed, so nothing is lost (some text may then appear twice).
    fn finish(
        mut self,
        pipeline: Option<&mut Pipeline>,
        dictation: &Dictation,
        delivery: Delivery,
        lost_clips: &LostClips,
    ) -> Transcribed {
        let tail = &dictation.samples;
        self.push(tail);
        if is_deaf(self.seconds, self.peak_level) {
            return heard_nothing(dictation);
        }
        let streamer = self.streamer.take().unwrap_or_default();
        let done = if is_deaf_take(streamer.rest()) {
            // Nothing to hear, but a number held back is still to be typed.
            held_number(streamer.flush())
        } else {
            finish_stream(pipeline, streamer, lost_clips)
        };
        let Event::Transcribed(last) = done.event else {
            return done;
        };
        let whole = format!("{}{last}", self.typed);
        let outcome = match (self.typed.is_empty(), self.has_insertion_failed) {
            (true, _) => done.outcome,
            (false, true) => Outcome::Failed,
            (false, false) => Outcome::Inserted,
        };
        let text = if delivery == Delivery::Clipboard || self.has_insertion_failed {
            whole.clone()
        } else {
            last
        };
        Transcribed {
            event: Event::Transcribed(text),
            outcome,
            engine: self.engine.or(done.engine),
            length: whole.chars().count(),
            whole,
            alert: None,
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
        Alert(Alert),
        Caption(Caption),
    }

    /// Records what the user would see and hear.
    struct Cues(Arc<Mutex<Vec<Cue>>>);
    impl Feedback for Cues {
        fn show(&mut self, phase: Phase) {
            self.0.lock().unwrap().push(Cue::Show(phase));
        }
        fn level(&mut self, _level: f32) {}
        fn alert(&mut self, alert: Alert) {
            self.0.lock().unwrap().push(Cue::Alert(alert));
        }
        fn caption(&mut self, caption: &Caption) {
            self.0.lock().unwrap().push(Cue::Caption(caption.clone()));
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
        controller.send(Event::TriggerDown(start));
        controller.send(Event::TriggerUp(start + Duration::from_secs(seconds)));
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
        controller.send(Event::TriggerDown(Instant::now()));
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
        assert!(cues.contains(&Cue::Alert(Alert::microphone_heard_nothing(
            "Microphone heard nothing (MacBook Pro Microphone)"
        ))));
    }

    /// Says the same timed words whatever it hears; no plain text.
    struct Words(Vec<whispy_core::Word>);
    impl Transcriber for Words {
        fn name(&self) -> &'static str {
            "words"
        }
        fn transcribe(&mut self, _: &[f32]) -> Result<String, whispy_core::Error> {
            Ok(String::new())
        }
        fn transcribe_timed(
            &mut self,
            _: &[f32],
        ) -> Result<Option<Vec<whispy_core::Word>>, whispy_core::Error> {
            Ok(Some(self.0.clone()))
        }
    }

    /// A dictation whose passes committed « Rappelle moi à quatorze heures »
    /// (the number held back), then went deaf.
    fn live_holding_a_number() -> (LiveDictation, Pipeline) {
        let word = |text: &str, start_s, end_s| whispy_core::Word {
            text: text.to_string(),
            start_s,
            end_s,
        };
        let words = vec![
            word("Rappelle", 0.2, 0.5),
            word("moi", 0.6, 0.9),
            word("à", 1.0, 1.2),
            word("quatorze", 1.3, 1.6),
            word("heures", 1.7, 2.1),
        ];
        let mut pipeline = pipeline(Words(words)).unwrap();
        let voiced: Vec<f32> = (0..(2.2 * 16_000.0) as usize)
            .map(|i| {
                let t = i as f32 / 16_000.0;
                (1..=10)
                    .map(|h| 0.03 * (2.0 * std::f32::consts::PI * 150.0 * h as f32 * t).sin())
                    .sum::<f32>()
            })
            .collect();
        let mut live = LiveDictation::started(true);
        let mut typed = String::new();
        for block in [voiced, tone(3.0, 0.006)] {
            live.push(&block);
            let streamer = live.streamer.as_mut().unwrap();
            if streamer.is_pass_due() {
                typed.push_str(&streamer.pass(&mut pipeline).unwrap().typed);
            }
        }
        assert_eq!(typed, "Rappelle moi à", "the number is held back");
        assert!(is_deaf_take(live.streamer.as_ref().unwrap().rest()));
        live.typed = typed;
        (live, pipeline)
    }

    fn a_stop() -> Dictation {
        Dictation {
            samples: Vec::new(),
            device: None,
            released_at: Instant::now(),
            trigger: Source::Fn,
        }
    }

    #[test]
    fn a_number_held_back_is_typed_when_the_stop_is_a_deaf_take() {
        let (live, mut pipeline) = live_holding_a_number();
        let lost = LostClips { directory: None };
        let done = live.finish(Some(&mut pipeline), &a_stop(), Delivery::Paste, &lost);
        assert_eq!(done.event, Event::Transcribed(" 14 heures".to_string()));
        assert_eq!(done.outcome, Outcome::Inserted);
    }

    #[test]
    fn a_number_held_back_is_typed_when_no_engine_is_loaded_at_the_stop() {
        let (live, _) = live_holding_a_number();
        let lost = LostClips { directory: None };
        let done = live.finish(None, &a_stop(), Delivery::Paste, &lost);
        assert_eq!(done.event, Event::Transcribed(" 14 heures".to_string()));
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
        // (The models may still be loading: that alert is not the deaf-take one.)
        assert!(!cues.lock().unwrap().iter().any(
            |cue| matches!(cue, Cue::Alert(alert) if alert.subtitle == "Microphone heard nothing")
        ));
        assert!(shown
            .try_iter()
            .all(|status| !status.note.unwrap_or_default().contains("heard nothing")));
    }

    #[test]
    fn the_pill_follows_the_recording_and_alerts_on_heard_nothing() {
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
        wait_for("the pill never hid", || {
            cues.lock().unwrap().last() == Some(&Cue::Show(Phase::Hidden))
        });
        controller.stop();
        let shown: Vec<Cue> = cues
            .lock()
            .unwrap()
            .iter()
            .filter(|cue| matches!(cue, Cue::Show(_)))
            .cloned()
            .collect();
        assert_eq!(
            shown,
            vec![Cue::Show(Phase::Recording), Cue::Show(Phase::Hidden)]
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
            heard_cues
                .lock()
                .unwrap()
                .iter()
                .any(|cue| matches!(cue, Cue::Alert(_)))
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
        controller.send_from(Event::TriggerDown(Instant::now()), Source::Socket);
        controller.send_from(
            Event::TriggerUp(Instant::now() + Duration::from_secs(4)),
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
        assert_eq!(
            dispatch(&controller.inputs, Request::Last),
            "{\"text\":null}"
        );
        // No level before a recording: the capture's sink is not heard at rest.
        controller.inputs.send(Input::Level(0.9)).unwrap();
        assert!(dispatch(&controller.inputs, Request::Status).ends_with("\"level\":0.000}"));
        assert_eq!(dispatch(&controller.inputs, Request::Start), "ok");
        // The pill's level is read on the socket while recording.
        controller.inputs.send(Input::Level(0.42)).unwrap();
        let recording = dispatch(&controller.inputs, Request::Status);
        assert!(recording.contains("\"state\":\"recording\""), "{recording}");
        assert!(recording.ends_with("\"level\":0.420}"), "{recording}");
        // Immediately: still a hold, not a tap.
        assert_eq!(dispatch(&controller.inputs, Request::Stop), "ok");
        let (text, _) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(text, "32000 samples");
        wait_for("never idle", || {
            dispatch(&controller.inputs, Request::Status).contains("\"state\":\"idle\"")
        });
        // The level falls back once the recording ends; the text is kept in memory.
        assert!(dispatch(&controller.inputs, Request::Status).ends_with("\"level\":0.000}"));
        assert_eq!(
            dispatch(&controller.inputs, Request::Last),
            "{\"text\":\"32000 samples\"}"
        );
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

    /// Runs `inputs` through a controller and returns the alerts raised and the last status.
    fn raised(inputs: Vec<Input>) -> (Vec<Alert>, Status) {
        let (delivered, _inserted) = mpsc::channel();
        let cues = Arc::new(Mutex::new(Vec::new()));
        let (statuses, shown) = mpsc::channel();
        let controller = Controller::start(
            || Clip(Vec::new()),
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            Cues(Arc::clone(&cues)),
            move |status: &Status| {
                let _ = statuses.send(status.clone());
            },
        );
        for input in inputs {
            controller.inputs.send(input).unwrap();
        }
        controller.stop();
        let alerts = cues
            .lock()
            .unwrap()
            .iter()
            .filter_map(|cue| match cue {
                Cue::Alert(alert) => Some(alert.clone()),
                Cue::Show(_) | Cue::Caption(_) => None,
            })
            .collect();
        (alerts, shown.try_iter().last().unwrap())
    }

    #[test]
    fn a_failed_model_load_raises_v1s_alert() {
        let (alerts, status) = raised(vec![Input::ModelsLoaded(Err("offline".into()))]);
        assert_eq!(alerts.len(), 1);
        assert_eq!(alerts[0].subtitle, "Model failed to load");
        assert_eq!(
            alerts[0].message,
            "offline \u{2014} check your internet connection, then use Restart from the Whispy menu."
        );
        assert_eq!(status.permission_pane, None);
        assert_eq!(status.note.as_deref(), Some(alerts[0].message.as_str()));
    }

    #[test]
    fn a_permission_alert_carries_its_pane_to_the_status() {
        let (alerts, status) = raised(vec![Input::Alert(Alert::missing_permission(
            "input_monitoring",
            "no tap",
        ))]);
        assert_eq!(alerts[0].subtitle, "Missing permission");
        assert_eq!(status.permission_pane, Some(Pane::InputMonitoring));
        assert_eq!(status.note.as_deref(), Some("no tap"));

        let denied = insertion_alert("macOS refused the paste: grant Accessibility to Whispy V2")
            .expect("an Accessibility refusal is an alert");
        assert_eq!(denied.subtitle, "Can't type into apps");
        assert_eq!(denied.pane, Some(Pane::Accessibility));
        assert_eq!(insertion_alert("the clipboard is busy"), None);
        let (_, status) = raised(vec![Input::Alert(denied)]);
        assert_eq!(status.permission_pane, Some(Pane::Accessibility));
    }

    #[test]
    fn an_unopenable_microphone_raises_no_microphone() {
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
        let cues = Arc::new(Mutex::new(Vec::new()));
        let controller = Controller::start(
            || Broken,
            || pipeline(Echo),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            Cues(Arc::clone(&cues)),
            |_: &Status| {},
        );
        controller.send(Event::TriggerDown(Instant::now()));
        controller.stop();
        let cues = cues.lock().unwrap();
        let alert = cues
            .iter()
            .find_map(|cue| match cue {
                Cue::Alert(alert) => Some(alert),
                Cue::Show(_) | Cue::Caption(_) => None,
            })
            .expect("an alert");
        assert_eq!(alert.subtitle, "No microphone available");
        assert!(alert.message.contains("no input device"));
        assert!(alert
            .message
            .ends_with("check your input device, then try again."));
    }

    #[test]
    fn the_watchdog_stop_and_a_dictation_over_loading_models_have_v1s_texts() {
        let stop = Action::StopCaptureAndTranscribe;
        let watchdog = alert_for(&stop, true, true, false).unwrap();
        assert_eq!(watchdog.subtitle, "Dictation stopped");
        assert_eq!(
            watchdog.message,
            "Dictation stopped after 5 minutes. Any transcribed text was copied to the clipboard."
        );
        let loading = alert_for(&stop, false, false, false).unwrap();
        assert_eq!(loading.subtitle, "Model still loading");
        assert_eq!(
            loading.message,
            "Whispy is still loading the transcription model \u{2014} try again in a moment."
        );
        // Loaded, or failed (that has its own alert): nothing more to say.
        assert_eq!(alert_for(&stop, false, true, false), None);
        assert_eq!(alert_for(&stop, false, false, true), None);
        assert_eq!(
            alert_for(&Action::DiscardCapture, false, false, false),
            None
        );
    }

    /// Harmonic stack: reads as voiced to WebRTC VAD.
    fn voiced(seconds: f32) -> Vec<f32> {
        (0..(seconds * 16_000.0) as usize)
            .map(|i| {
                let t = i as f32 / 16_000.0;
                (1..=10)
                    .map(|h| 0.03 * (2.0 * std::f32::consts::PI * 150.0 * h as f32 * t).sin())
                    .sum::<f32>()
            })
            .collect()
    }

    /// Two sentences with a one-second pause between them.
    /// « Hello. », a 1 s pause, « there », then 1 s of silence before the stop.
    fn two_sentences() -> Vec<f32> {
        [
            voiced(1.5),
            vec![0.0; 16_000],
            voiced(1.2),
            vec![0.0; 16_000],
        ]
        .concat()
    }

    /// A microphone that hands out its clip 50 ms per take, the rest at the stop.
    struct Streamed {
        clip: Vec<f32>,
        taken: usize,
    }
    impl Capture for Streamed {
        fn start(&mut self) -> Result<(), String> {
            self.taken = 0;
            Ok(())
        }
        fn take_recorded(&mut self) -> Vec<f32> {
            let end = (self.taken + 800).min(self.clip.len());
            let block = self.clip[self.taken..end].to_vec();
            self.taken = end;
            block
        }
        fn stop(&mut self) -> Vec<f32> {
            let rest = self.clip[self.taken..].to_vec();
            self.taken = self.clip.len();
            rest
        }
    }

    /// A timed engine that hears the clip: each voiced run is a word, named by
    /// its length (1.5 s « Hello. », 1.2 s « there »); a run still going at the
    /// window's end is not heard yet. The plain engine (hold mode, the setting
    /// off, the stop's second opinion) hears the same words.
    struct Rolling;
    impl Transcriber for Rolling {
        fn name(&self) -> &'static str {
            "rolling"
        }
        fn transcribe(&mut self, samples: &[f32]) -> Result<String, whispy_core::Error> {
            let words = self.transcribe_timed(samples)?.unwrap_or_default();
            let texts: Vec<String> = words.into_iter().map(|word| word.text).collect();
            Ok(texts.join(" "))
        }
        fn transcribe_timed(
            &mut self,
            samples: &[f32],
        ) -> Result<Option<Vec<whispy_core::Word>>, whispy_core::Error> {
            let end_s = samples.len() as f32 / SAMPLE_RATE;
            let loud = samples
                .chunks(160)
                .map(|frame| frame.iter().map(|s| s.abs()).sum::<f32>() / frame.len() as f32 > 0.02)
                .chain(std::iter::once(false));
            let (mut words, mut run_start) = (Vec::new(), None);
            for (i, is_loud) in loud.enumerate() {
                match (is_loud, run_start) {
                    (true, None) => run_start = Some(i),
                    (false, Some(first)) => {
                        let (start_s, end) = (first as f32 / 100.0, i as f32 / 100.0);
                        if end < end_s - 0.05 {
                            words.push(whispy_core::Word {
                                text: if end - start_s > 1.35 {
                                    "Hello."
                                } else {
                                    "there"
                                }
                                .into(),
                                start_s,
                                end_s: end,
                            });
                        }
                        run_start = None;
                    }
                    _ => {}
                }
            }
            Ok(Some(words))
        }
    }

    /// A controller over [`two_sentences`], in `mode`, with type while speaking `is_on`.
    fn live_controller(
        mode: crate::settings::TriggerMode,
        is_on: bool,
        inserter: impl Inserter + 'static,
    ) -> Controller {
        live_controller_with(mode, is_on, inserter, crate::feedback::NoFeedback)
    }

    fn live_controller_with(
        mode: crate::settings::TriggerMode,
        is_on: bool,
        inserter: impl Inserter + 'static,
        feedback: impl Feedback + 'static,
    ) -> Controller {
        let controller = Controller::start(
            || Streamed {
                clip: two_sentences(),
                taken: 0,
            },
            || pipeline(Rolling),
            inserter,
            LostClips { directory: None },
            no_journal(),
            feedback,
            |_: &Status| {},
        );
        controller
            .inputs
            .send(Input::TypeWhileSpeaking(is_on))
            .unwrap();
        controller.send(Event::Settings(mode));
        controller
    }

    /// The microphone's level beats for the whole clip, each draining 50 ms. A
    /// pass is due every 12 beats (0.6 s): the worker gets a moment after each
    /// group so the passes run apart, as they would at the speed of speech.
    fn play_the_clip(controller: &Controller) {
        let beats = two_sentences().len() / 800;
        for beat in 1..=beats {
            controller.inputs.send(Input::Level(0.5)).unwrap();
            if beat % 12 == 0 {
                thread::sleep(Duration::from_millis(60));
            }
        }
    }

    fn press(controller: &Controller, at: Instant) {
        controller.send(Event::TriggerDown(at));
        controller.send(Event::TriggerUp(at + Duration::from_millis(100)));
    }

    #[test]
    fn toggle_types_the_first_sentence_before_the_stop_then_the_rest() {
        use crate::settings::TriggerMode;
        let (delivered, inserted) = mpsc::channel();
        let controller = live_controller(TriggerMode::Toggle, true, Recorder(delivered));
        let start = Instant::now();
        press(&controller, start);
        play_the_clip(&controller);
        let first = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(first, ("Hello.".to_string(), Delivery::Paste));
        assert!(
            inserted.try_recv().is_err(),
            "only the first sentence before the stop"
        );
        press(&controller, start + Duration::from_secs(5));
        let last = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        // The stop hears « there » in the context of « Hello. », and a capital
        // follows the typed period.
        assert_eq!(last, (" There".to_string(), Delivery::Paste));
        controller.stop();
        assert!(inserted.try_recv().is_err(), "nothing typed twice");
    }

    #[test]
    fn hold_mode_and_the_setting_off_insert_once_at_the_end() {
        use crate::settings::TriggerMode;
        for (mode, is_on) in [(TriggerMode::Hold, true), (TriggerMode::Toggle, false)] {
            let (delivered, inserted) = mpsc::channel();
            let controller = live_controller(mode, is_on, Recorder(delivered));
            let start = Instant::now();
            controller.send(Event::TriggerDown(start));
            play_the_clip(&controller);
            thread::sleep(Duration::from_millis(200));
            assert!(
                inserted.try_recv().is_err(),
                "{mode:?}: nothing typed before the stop"
            );
            match mode {
                TriggerMode::Hold => {
                    controller.send(Event::TriggerUp(start + Duration::from_secs(5)))
                }
                TriggerMode::Toggle => {
                    controller.send(Event::TriggerUp(start + Duration::from_millis(100)));
                    press(&controller, start + Duration::from_secs(5));
                }
            }
            let (text, delivery) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
            assert_eq!(
                (text.as_str(), delivery),
                ("Hello. there", Delivery::Paste),
                "{mode:?}"
            );
            controller.stop();
            assert!(inserted.try_recv().is_err(), "{mode:?}: one insertion");
        }
    }

    #[test]
    fn the_watchdog_stop_puts_the_whole_dictation_on_the_clipboard() {
        use crate::settings::TriggerMode;
        let (delivered, inserted) = mpsc::channel();
        let controller = live_controller(TriggerMode::Toggle, true, Recorder(delivered));
        let start = Instant::now();
        press(&controller, start);
        play_the_clip(&controller);
        assert_eq!(
            inserted.recv_timeout(Duration::from_secs(5)).unwrap().0,
            "Hello."
        );
        controller.send(Event::Tick(start + RECORDING_LIMIT));
        let last = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(last, ("Hello. There".to_string(), Delivery::Clipboard));
        controller.stop();
    }

    #[test]
    fn a_passage_that_could_not_be_typed_is_not_lost() {
        use crate::settings::TriggerMode;
        /// Refuses its first insertion, like a paste macOS refused once.
        struct RefusesFirst(Sender<(String, Delivery)>, bool);
        impl Inserter for RefusesFirst {
            fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String> {
                if !self.1 {
                    self.1 = true;
                    return Err("the clipboard is busy".into());
                }
                let _ = self.0.send((text.to_string(), delivery));
                Ok(())
            }
        }
        let (delivered, inserted) = mpsc::channel();
        let controller = live_controller(TriggerMode::Toggle, true, RefusesFirst(delivered, false));
        let start = Instant::now();
        press(&controller, start);
        play_the_clip(&controller);
        thread::sleep(Duration::from_millis(200));
        press(&controller, start + Duration::from_secs(5));
        let last = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(last, ("Hello. There".to_string(), Delivery::Paste));
        controller.stop();
    }

    #[test]
    fn a_caption_reaches_the_pill_while_recording_in_toggle_mode() {
        use crate::settings::TriggerMode;
        let (delivered, _inserted) = mpsc::channel();
        let cues = Arc::new(Mutex::new(Vec::new()));
        let controller = live_controller_with(
            TriggerMode::Toggle,
            true,
            Recorder(delivered),
            Cues(Arc::clone(&cues)),
        );
        press(&controller, Instant::now());
        play_the_clip(&controller);
        wait_for("no caption with the typed sentence", || {
            cues.lock().unwrap().iter().any(|cue| {
                matches!(cue, Cue::Caption(caption)
                    if caption.committed == "Hello." && caption.provisional == "there")
            })
        });
        let captions: Vec<Caption> = cues
            .lock()
            .unwrap()
            .iter()
            .filter_map(|cue| match cue {
                Cue::Caption(caption) => Some(caption.clone()),
                _ => None,
            })
            .collect();
        assert!(
            captions.windows(2).all(|pair| pair[0] != pair[1]),
            "an unchanged caption is not sent again: {captions:?}"
        );
        controller.stop();
    }

    #[test]
    fn a_late_caption_after_the_stop_is_dropped() {
        let cues = Arc::new(Mutex::new(Vec::new()));
        let controller = Controller::start(
            || Clip(Vec::new()),
            || pipeline(Echo),
            Recorder(mpsc::channel().0),
            LostClips { directory: None },
            no_journal(),
            Cues(Arc::clone(&cues)),
            |_: &Status| {},
        );
        let caption = Caption {
            committed: "Hello.".into(),
            provisional: String::new(),
        };
        controller.inputs.send(Input::Caption(caption)).unwrap();
        controller.stop();
        assert!(
            !cues
                .lock()
                .unwrap()
                .iter()
                .any(|cue| matches!(cue, Cue::Caption(_))),
            "nothing is recording"
        );
    }

    #[test]
    fn hold_mode_and_the_setting_off_show_the_caption_but_type_nothing_live() {
        use crate::settings::TriggerMode;
        for (mode, is_on) in [(TriggerMode::Hold, true), (TriggerMode::Toggle, false)] {
            let (delivered, inserted) = mpsc::channel();
            let cues = Arc::new(Mutex::new(Vec::new()));
            let controller =
                live_controller_with(mode, is_on, Recorder(delivered), Cues(Arc::clone(&cues)));
            let start = Instant::now();
            controller.send(Event::TriggerDown(start));
            play_the_clip(&controller);
            wait_for("no caption while recording", || {
                cues.lock().unwrap().iter().any(|cue| {
                    matches!(cue, Cue::Caption(caption)
                        if caption.committed == "Hello." && caption.provisional == "there")
                })
            });
            assert!(
                inserted.try_recv().is_err(),
                "{mode:?}: nothing typed while speaking"
            );
            match mode {
                TriggerMode::Hold => {
                    controller.send(Event::TriggerUp(start + Duration::from_secs(5)))
                }
                TriggerMode::Toggle => {
                    controller.send(Event::TriggerUp(start + Duration::from_millis(100)));
                    press(&controller, start + Duration::from_secs(5));
                }
            }
            let (text, delivery) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
            assert_eq!(
                (text.as_str(), delivery),
                ("Hello. there", Delivery::Paste),
                "{mode:?}"
            );
            controller.stop();
            assert!(inserted.try_recv().is_err(), "{mode:?}: one insertion");
        }
    }

    #[test]
    fn the_recorder_streams_in_toggle_mode_and_discards_the_stream() {
        let now = Instant::now();
        let recording = |mode| State::Recording {
            mode,
            pressed_at: now,
            started_at: now,
        };
        let (jobs, queue) = mpsc::channel();
        let mut recorder = super::Recorder {
            capture: Streamed {
                clip: two_sentences(),
                taken: 0,
            },
            is_recording: false,
            trigger: Source::Fn,
            is_typing_while_speaking: true,
        };
        recorder
            .perform(Action::StartCapture, recording(Mode::Toggle), &jobs)
            .unwrap();
        recorder.send_audio(&jobs);
        recorder
            .perform(Action::DiscardCapture, State::Idle, &jobs)
            .unwrap();
        recorder.send_audio(&jobs);
        let kinds: Vec<&str> = queue
            .try_iter()
            .map(|job| match job {
                Job::StartStream { types_live: true } => "start-live",
                Job::StartStream { types_live: false } => "start",
                Job::StreamAudio(samples) if samples.len() == 800 => "audio",
                Job::DiscardStream => "discard",
                _ => "other",
            })
            .collect();
        assert_eq!(kinds, ["start-live", "audio", "discard"]);

        // Hold mode is captioned but never types live.
        recorder
            .perform(Action::StartCapture, recording(Mode::Hold), &jobs)
            .unwrap();
        recorder.send_audio(&jobs);
        assert!(matches!(
            queue.try_recv(),
            Ok(Job::StartStream { types_live: false })
        ));
        assert!(matches!(queue.try_recv(), Ok(Job::StreamAudio(_))));
    }

    #[test]
    fn a_discarded_streaming_dictation_types_nothing_more() {
        let (delivered, inserted) = mpsc::channel();
        let (inputs, _controller_inputs) = mpsc::channel();
        let (jobs, worker) = spawn_worker(
            || pipeline(Rolling),
            Recorder(delivered),
            LostClips { directory: None },
            no_journal(),
            inputs,
        );
        jobs.send(Job::StartStream { types_live: true }).unwrap();
        // The first pass: one hypothesis, nothing committed yet.
        jobs.send(Job::StreamAudio(voiced(0.6))).unwrap();
        thread::sleep(Duration::from_millis(100));
        jobs.send(Job::DiscardStream).unwrap();
        // The second pass would have committed the first sentence.
        jobs.send(Job::StreamAudio(voiced(0.6))).unwrap();
        thread::sleep(Duration::from_millis(100));
        drop(jobs);
        worker.join().unwrap();
        assert!(
            inserted.try_recv().is_err(),
            "nothing typed after a discard"
        );
    }

    #[test]
    fn the_pass_log_line_holds_counts_and_no_text() {
        let stats = PassStats {
            window_s: 12.44,
            took_s: 0.381,
            words: 23,
            stable: 18,
            committed_words: 11,
            forced: false,
            audio_end_s: 3.0,
        };
        assert_eq!(
            pass_line(&stats, true),
            "stream pass: live=yes window=12.4s took=0.38s words=23 stable=18 committed=11 forced=no"
        );
        let forced = PassStats {
            forced: true,
            ..stats
        };
        assert!(pass_line(&forced, false).starts_with("stream pass: live=no "));
        assert!(pass_line(&forced, true).ends_with("forced=yes"));
    }

    #[test]
    fn the_caption_tail_is_cut_on_a_word_and_a_char_boundary() {
        assert_eq!(caption_tail("short text", 120), "short text");
        assert_eq!(caption_tail("one two three four", 12), "three four");
        assert_eq!(caption_tail("one two three four", 11), "three four");
        // A single long word has no boundary to cut on: the end of it stays.
        assert_eq!(caption_tail("abcdefghij", 4), "ghij");
        // Multi-byte chars are never split.
        let tail = caption_tail("été à Zürich, déjà là", 7);
        assert!(tail.chars().count() <= 7, "{tail}");
        assert!("été à Zürich, déjà là".ends_with(&tail));
    }
}

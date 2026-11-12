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
//! dictation records, the controller drains the microphone at each level beat,
//! cuts the audio at the speaker's pauses ([`LiveSplitter`]) and queues each
//! piece; the worker transcribes and types it at once. The stopping press
//! queues the last piece, whose text goes back through the machine like any
//! dictation's. One queue, one worker: pieces are typed in recording order and
//! never two at once.

use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use whispy_core::split::LiveSplitter;
use whispy_core::{Pipeline, Strategy};

use crate::feedback::{phase_of, Feedback, Phase};
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

#[derive(Debug)]
pub enum Input {
    Event(Event, Source),
    ModelsLoaded(Result<(), String>),
    /// Something to tell the user that is not a state change (an insertion failure).
    Note(String),
    /// A [`Note`](Input::Note) that is also one of V1's notifications (see [`Alert`]).
    Alert(Alert),
    /// The input level of the recording, from the capture's level sink. Also the
    /// beat at which a dictation typed while spoken is drained and cut.
    Level(f32),
    /// V1's `type_while_speaking`: in toggle mode, type each piece as soon as it
    /// is transcribed. Applies from the next dictation.
    TypeWhileSpeaking(bool),
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
    /// A piece cut at a pause while the dictation records: transcribe and type it now.
    TypePiece(Vec<f32>),
    /// The end of a dictation typed while spoken: its text goes back through the machine.
    TranscribeLastPiece {
        dictation: Dictation,
        delivery: Delivery,
    },
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
        splitter: None,
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
                recorder.send_closed_pieces(&jobs);
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

/// The controller's side of a recording: the microphone and, while a toggle
/// dictation is typed as it is spoken, the splitter that cuts it at pauses.
struct Recorder<C: Capture> {
    capture: C,
    splitter: Option<LiveSplitter>,
    /// What started the current recording, for the journal.
    trigger: Source,
    is_typing_while_speaking: bool,
}

impl<C: Capture> Recorder<C> {
    /// Runs `action`; `state` is the machine's state right after deciding it.
    fn perform(&mut self, action: Action, state: State, jobs: &Sender<Job>) -> Result<(), String> {
        match action {
            Action::StartCapture => {
                self.splitter = None;
                self.capture
                    .start()
                    .map_err(|error| format!("The microphone could not be opened: {error}"))?;
                // Decided once, at the start: a setting flipped mid-dictation
                // must not leave half of it typed live and the rest at the stop.
                // Hold mode never types live: the trigger is held down meanwhile.
                let is_toggle = matches!(
                    state,
                    State::Recording {
                        mode: Mode::Toggle,
                        ..
                    }
                );
                if is_toggle && self.is_typing_while_speaking {
                    self.splitter = Some(LiveSplitter::new());
                }
                Ok(())
            }
            Action::StopCaptureAndTranscribe => {
                let released_at = Instant::now();
                let rest = self.capture.stop();
                let delivery = match state {
                    State::Transcribing { delivery } => delivery,
                    _ => Delivery::Paste,
                };
                let mut dictation = Dictation {
                    samples: rest,
                    device: self.capture.device_name(),
                    released_at,
                    trigger: self.trigger,
                };
                let job = match self.splitter.take() {
                    None => Job::Transcribe(dictation),
                    Some(mut splitter) => {
                        for piece in splitter.push(&dictation.samples) {
                            let _ = jobs.send(Job::TypePiece(piece));
                        }
                        dictation.samples = splitter.finish();
                        Job::TranscribeLastPiece {
                            dictation,
                            delivery,
                        }
                    }
                };
                let _ = jobs.send(job);
                Ok(())
            }
            Action::DiscardCapture => {
                self.splitter = None;
                self.capture.stop();
                Ok(())
            }
            Action::Insert { text, delivery } => {
                let _ = jobs.send(Job::Insert { text, delivery });
                Ok(())
            }
        }
    }

    /// While a dictation is typed as it is spoken: drains the microphone and
    /// queues each piece a pause closed.
    fn send_closed_pieces(&mut self, jobs: &Sender<Job>) {
        let Some(splitter) = self.splitter.as_mut() else {
            return;
        };
        for piece in splitter.push(&self.capture.take_recorded()) {
            let _ = jobs.send(Job::TypePiece(piece));
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
            // The dictation being typed while spoken, between its pieces.
            let mut live = LiveDictation::default();
            for job in receiver {
                let (done, dictation, duration_s) = match job {
                    Job::TypePiece(samples) => {
                        let failure = live.type_piece(
                            pipeline.as_mut(),
                            &samples,
                            &mut inserter,
                            &lost_clips,
                        );
                        if let Some(error) = failure {
                            let _ = controller.send(insertion_input(error));
                        }
                        continue;
                    }
                    Job::Transcribe(dictation) => {
                        let done = transcribe(pipeline.as_mut(), &dictation, &lost_clips);
                        let duration_s = dictation.samples.len() as f32 / SAMPLE_RATE;
                        (done, dictation, duration_s)
                    }
                    Job::TranscribeLastPiece {
                        dictation,
                        delivery,
                    } => {
                        let finished = std::mem::take(&mut live);
                        let duration_s =
                            finished.seconds + dictation.samples.len() as f32 / SAMPLE_RATE;
                        let done =
                            finished.finish(pipeline.as_mut(), &dictation, delivery, &lost_clips);
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

/// A dictation typed while spoken, between its first piece and its stop.
#[derive(Default)]
struct LiveDictation {
    /// The text handed to the inserter so far, pieces joined by a space (the
    /// text of a piece whose insertion failed included).
    typed: String,
    /// The audio of the pieces so far, for the journal and the deaf-take check.
    seconds: f32,
    peak_level: f32,
    engine: Option<&'static str>,
    has_insertion_failed: bool,
}

impl LiveDictation {
    /// Transcribes a piece and types it after the text before it. Returns the
    /// insertion error the user must hear about: the first of the dictation only.
    fn type_piece(
        &mut self,
        pipeline: Option<&mut Pipeline>,
        samples: &[f32],
        inserter: &mut impl Inserter,
        lost_clips: &LostClips,
    ) -> Option<String> {
        self.seconds += samples.len() as f32 / SAMPLE_RATE;
        self.peak_level = self.peak_level.max(peak_level(samples));
        if is_deaf_take(samples) {
            return None;
        }
        let done = transcribe_samples(pipeline, samples, lost_clips);
        let Event::Transcribed(text) = done.event else {
            return None;
        };
        if text.trim().is_empty() {
            return None;
        }
        let piece = self.next_piece(&text);
        self.typed.push_str(&piece);
        self.engine = self.engine.or(done.engine);
        let error = inserter.deliver(&piece, Delivery::Paste).err()?;
        log::line(&format!("insertion of a piece failed: {error}"));
        let is_first_failure = !self.has_insertion_failed;
        self.has_insertion_failed = true;
        is_first_failure.then_some(error)
    }

    /// `text` as it follows what was typed: a space between pieces, none before the first.
    fn next_piece(&self, text: &str) -> String {
        if self.typed.is_empty() {
            text.trim().to_string()
        } else {
            format!(" {}", text.trim())
        }
    }

    /// The last piece, at the stop. Its event carries what the machine inserts:
    /// the last piece's text; the whole dictation when it goes to the clipboard
    /// (the watchdog), or when a piece could not be typed, so nothing is lost
    /// (some text may then appear twice).
    fn finish(
        self,
        pipeline: Option<&mut Pipeline>,
        dictation: &Dictation,
        delivery: Delivery,
        lost_clips: &LostClips,
    ) -> Transcribed {
        let tail = &dictation.samples;
        let seconds = self.seconds + tail.len() as f32 / SAMPLE_RATE;
        if is_deaf(seconds, self.peak_level.max(peak_level(tail))) {
            return heard_nothing(dictation);
        }
        let done = if is_deaf_take(tail) {
            Transcribed::without_text(Event::Transcribed(String::new()), Outcome::Empty)
        } else {
            transcribe_samples(pipeline, tail, lost_clips)
        };
        let Event::Transcribed(tail_text) = &done.event else {
            return done;
        };
        let last_piece = if tail_text.trim().is_empty() {
            String::new()
        } else {
            self.next_piece(tail_text)
        };
        let whole = format!("{}{last_piece}", self.typed);
        let outcome = match (self.typed.is_empty(), self.has_insertion_failed) {
            (true, _) => done.outcome,
            (false, true) => Outcome::Failed,
            (false, false) => Outcome::Inserted,
        };
        let text = if delivery == Delivery::Clipboard || self.has_insertion_failed {
            whole.clone()
        } else {
            last_piece
        };
        Transcribed {
            event: Event::Transcribed(text),
            outcome,
            engine: self.engine.or(done.engine),
            length: whole.chars().count(),
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
                Cue::Show(_) => None,
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
                Cue::Show(_) => None,
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
    fn two_sentences() -> Vec<f32> {
        [
            voiced(1.5),
            vec![0.0; 16_000],
            voiced(1.5),
            vec![0.0; 3_200],
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

    /// Says « pieceN » for its Nth call.
    struct Numbered(AtomicUsize);
    impl Transcriber for Numbered {
        fn name(&self) -> &'static str {
            "numbered"
        }
        fn transcribe(&mut self, _samples: &[f32]) -> Result<String, whispy_core::Error> {
            Ok(format!(
                "piece{}",
                self.0.fetch_add(1, Ordering::SeqCst) + 1
            ))
        }
    }

    /// A controller over [`two_sentences`], in `mode`, with type while speaking `is_on`.
    fn live_controller(
        mode: crate::settings::TriggerMode,
        is_on: bool,
        inserter: impl Inserter + 'static,
    ) -> Controller {
        let controller = Controller::start(
            || Streamed {
                clip: two_sentences(),
                taken: 0,
            },
            || pipeline(Numbered(AtomicUsize::new(0))),
            inserter,
            LostClips { directory: None },
            no_journal(),
            crate::feedback::NoFeedback,
            |_: &Status| {},
        );
        controller
            .inputs
            .send(Input::TypeWhileSpeaking(is_on))
            .unwrap();
        controller.send(Event::Settings(mode));
        controller
    }

    /// The microphone's level beats for the whole clip: each drains 50 ms.
    fn play_the_clip(controller: &Controller) {
        for _ in 0..two_sentences().len() / 800 {
            controller.inputs.send(Input::Level(0.5)).unwrap();
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
        assert_eq!(first, ("piece1".to_string(), Delivery::Paste));
        assert!(
            inserted.try_recv().is_err(),
            "only the first sentence before the stop"
        );
        press(&controller, start + Duration::from_secs(5));
        let last = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(last, (" piece2".to_string(), Delivery::Paste));
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
                "{mode:?}: nothing before the stop"
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
                ("piece1", Delivery::Paste),
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
            "piece1"
        );
        controller.send(Event::Tick(start + RECORDING_LIMIT));
        let last = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(last, ("piece1 piece2".to_string(), Delivery::Clipboard));
        controller.stop();
    }

    #[test]
    fn a_piece_that_could_not_be_typed_is_not_lost() {
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
        assert_eq!(last, ("piece1 piece2".to_string(), Delivery::Paste));
        controller.stop();
    }
}

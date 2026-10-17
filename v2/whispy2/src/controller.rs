//! Runs the state machine against the outside world.
//!
//! Two threads. The controller thread owns the [`Machine`] and the microphone
//! and never blocks on a model: it only reacts to events. The worker thread
//! owns the [`Pipeline`] and the inserter, and runs one job at a time
//! (load the models, transcribe a dictation, insert its text), reporting each
//! result back to the controller as an event. A release is therefore never
//! waiting behind a transcription, and a transcription never runs twice at once.

use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread::{self, JoinHandle};
use std::time::{SystemTime, UNIX_EPOCH};

use whispy_core::{Pipeline, Strategy};

use crate::machine::{Action, Delivery, Event, Machine, Mode, State};

/// The microphone, as the controller sees it: 16 kHz mono out.
pub trait Capture {
    fn start(&mut self) -> Result<(), String>;
    /// Stops the recording and returns it, 16 kHz mono `f32`.
    fn stop(&mut self) -> Vec<f32>;
}

/// Puts text where the user is.
pub trait Inserter: Send {
    fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String>;
}

/// What the menu shows.
#[derive(Debug, Clone, PartialEq)]
pub struct Status {
    pub state: State,
    /// The last thing worth telling the user (loading, an error), if any.
    pub note: Option<String>,
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
}

#[derive(Debug)]
pub enum Input {
    Event(Event),
    ModelsLoaded(Result<(), String>),
    /// Something to tell the user that is not a state change (an insertion failure).
    Note(String),
    Quit,
}

enum Job {
    Transcribe(Vec<f32>),
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
    pub fn start<C, I>(
        make_capture: impl FnOnce() -> C + Send + 'static,
        load_pipeline: impl FnOnce() -> Result<Pipeline, whispy_core::Error> + Send + 'static,
        inserter: I,
        lost_clips: LostClips,
        show: impl Fn(&Status) + Send + 'static,
    ) -> Controller
    where
        C: Capture + 'static,
        I: Inserter + 'static,
    {
        let (inputs, receiver) = mpsc::channel();
        let (jobs, worker_thread) =
            spawn_worker(load_pipeline, inserter, lost_clips, inputs.clone());
        let controller_thread = thread::Builder::new()
            .name("whispy2-controller".into())
            .spawn(move || run(make_capture(), receiver, jobs, show))
            .expect("the controller thread could not be started");
        Controller {
            inputs,
            controller_thread,
            worker_thread,
        }
    }

    pub fn send(&self, event: Event) {
        // The controller only stops on Quit; a send after that has nowhere to go.
        let _ = self.inputs.send(Input::Event(event));
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
    jobs: Sender<Job>,
    show: impl Fn(&Status),
) {
    let mut machine = Machine::new();
    let mut status = Status {
        state: machine.state(),
        note: Some(LOADING_NOTE.into()),
    };
    show(&status);
    while let Ok(input) = receiver.recv() {
        let note = match input {
            Input::Quit => return,
            // Clears the loading note only: a problem reported meanwhile
            // (Input Monitoring missing) must stay on screen.
            Input::ModelsLoaded(Ok(())) => {
                (status.note.as_deref() == Some(LOADING_NOTE)).then_some(None)
            }
            Input::ModelsLoaded(Err(error)) | Input::Note(error) => Some(Some(error)),
            Input::Event(event) => {
                let note = note_for(&event);
                if let Some(action) = machine.handle(event) {
                    if let Err(error) = perform(action, &mut capture, &jobs) {
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
        let next = Status {
            state: machine.state(),
            note: note.unwrap_or_else(|| status.note.clone()),
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

fn perform(action: Action, capture: &mut impl Capture, jobs: &Sender<Job>) -> Result<(), String> {
    match action {
        Action::StartCapture => capture
            .start()
            .map_err(|error| format!("The microphone could not be opened: {error}")),
        Action::StopCaptureAndTranscribe => {
            let _ = jobs.send(Job::Transcribe(capture.stop()));
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

fn spawn_worker<I: Inserter + 'static>(
    load_pipeline: impl FnOnce() -> Result<Pipeline, whispy_core::Error> + Send + 'static,
    mut inserter: I,
    lost_clips: LostClips,
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
            for job in receiver {
                let event = match job {
                    Job::Transcribe(samples) => {
                        transcribe(pipeline.as_mut(), &samples, &lost_clips)
                    }
                    Job::Insert { text, delivery } => {
                        if let Err(error) = inserter.deliver(&text, delivery) {
                            eprintln!("[whispy2] insertion failed: {error}");
                            let _ = controller.send(Input::Note(error));
                        }
                        Event::Inserted
                    }
                };
                // After Quit nobody listens; keep draining until the queue closes.
                let _ = controller.send(Input::Event(event));
            }
        })
        .expect("the worker thread could not be started");
    (jobs, worker_thread)
}

fn transcribe(pipeline: Option<&mut Pipeline>, samples: &[f32], lost_clips: &LostClips) -> Event {
    let Some(pipeline) = pipeline else {
        keep_lost_clip(samples, lost_clips);
        return Event::TranscriptionFailed;
    };
    match pipeline.transcribe(samples) {
        Ok(transcript) => {
            // Empty text over audio the gates call speech is lost speech: keep it.
            if transcript.text.is_empty() && Strategy::Gated.prepare(samples).is_some() {
                keep_lost_clip(samples, lost_clips);
            }
            Event::Transcribed(transcript.text)
        }
        Err(error) => {
            eprintln!("[whispy2] transcription failed: {error}");
            keep_lost_clip(samples, lost_clips);
            Event::TranscriptionFailed
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
        eprintln!(
            "[whispy2] could not keep the lost clip at {}: {error}",
            path.display()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};
    use std::time::{Duration, Instant};
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

    struct Clip(Vec<f32>);
    impl Capture for Clip {
        fn start(&mut self) -> Result<(), String> {
            Ok(())
        }
        fn stop(&mut self) -> Vec<f32> {
            self.0.clone()
        }
    }

    struct Recorder(Sender<(String, Delivery)>);
    impl Inserter for Recorder {
        fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String> {
            let _ = self.0.send((text.to_string(), delivery));
            Ok(())
        }
    }

    #[test]
    fn a_held_dictation_reaches_the_inserter_and_the_menu_returns_to_idle() {
        let (delivered, inserted) = mpsc::channel();
        let statuses = Arc::new(Mutex::new(Vec::new()));
        let seen = Arc::clone(&statuses);
        let controller = Controller::start(
            || Clip(vec![0.0; 16_000]),
            || Ok(Pipeline::new(Box::new(Echo), None, Strategy::Raw)),
            Recorder(delivered),
            LostClips { directory: None },
            move |status: &Status| seen.lock().unwrap().push(status.state),
        );
        let start = Instant::now();
        controller.send(Event::FnDown(start));
        controller.send(Event::FnUp(start + Duration::from_secs(1)));
        let (text, delivery) = inserted.recv_timeout(Duration::from_secs(5)).unwrap();
        assert_eq!(text, "16000 samples");
        assert_eq!(delivery, Delivery::Paste);
        // The worker reports the insertion after delivering it: wait for idle.
        let deadline = Instant::now() + Duration::from_secs(5);
        while statuses.lock().unwrap().last() != Some(&State::Idle) {
            assert!(Instant::now() < deadline, "never back to idle");
            thread::sleep(Duration::from_millis(5));
        }
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
                Ok(Pipeline::new(Box::new(Echo), None, Strategy::Raw))
            },
            Recorder(delivered),
            LostClips { directory: None },
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
            || Ok(Pipeline::new(Box::new(Echo), None, Strategy::Raw)),
            Recorder(delivered),
            LostClips { directory: None },
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
}

//! The dictation state machine: every decision about the trigger key lives here.
//!
//! Pure: no clock, no thread, no I/O. Each event carries its own time and
//! the machine answers with at most one action for the caller to run. That
//! keeps the rules testable without a keyboard, and it is what V1 lacked:
//! its state was spread over the event tap, the engine and the audio thread,
//! and a release missed by one of them left the app frozen in RECORDING
//! (research: freeze recurrence, toggle trigger strand).

use std::time::{Duration, Instant};

use crate::settings::TriggerMode;

/// In Hold mode, a press released sooner than this is a slip, not a
/// dictation: it is discarded. V1's `min_recording_duration`. There is no
/// latch any more: hands-free dictation is Toggle mode, chosen in the menu.
pub const MIN_HOLD: Duration = Duration::from_millis(300);

/// A recording this long is stopped by the watchdog. V1's bound: five
/// minutes of recording almost always means a forgotten toggle.
pub const RECORDING_LIMIT: Duration = Duration::from_secs(300);

/// How a recording ends.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// The trigger is held; releasing it stops the recording (Hold mode).
    Hold,
    /// The next press of the trigger stops the recording (Toggle mode).
    Toggle,
}

/// Where the text goes once transcribed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Delivery {
    /// Pasted into the frontmost app.
    Paste,
    /// Left on the clipboard only. Used after the watchdog: minutes later, the
    /// field focused when the dictation started may not be focused any more.
    Clipboard,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum State {
    Idle,
    Recording {
        mode: Mode,
        pressed_at: Instant,
        started_at: Instant,
    },
    Transcribing {
        delivery: Delivery,
    },
    Inserting,
    /// V1 is running: the trigger belongs to it, and V2 ignores the key.
    Yielded,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Event {
    TriggerDown(Instant),
    TriggerUp(Instant),
    /// Another key went down while the trigger was held: it is a modifier
    /// (Fn+Delete, Fn+arrow), not a dictation. Never sent for the trigger
    /// key itself.
    OtherKeyDown,
    /// The trigger mode chosen in the menu. Applied when the machine is at
    /// rest: a dictation under way ends the way it began.
    Settings(TriggerMode),
    /// The clock, for the watchdog.
    Tick(Instant),
    /// The microphone could not be opened.
    CaptureFailed,
    Transcribed(String),
    TranscriptionFailed,
    Inserted,
    V1Running(bool),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    StartCapture,
    StopCaptureAndTranscribe,
    DiscardCapture,
    Insert { text: String, delivery: Delivery },
}

#[derive(Debug)]
pub struct Machine {
    state: State,
    is_key_held: bool,
    is_v1_running: bool,
    mode: TriggerMode,
    /// A mode received mid-dictation, applied at the next rest.
    pending_mode: Option<TriggerMode>,
}

impl Default for Machine {
    fn default() -> Self {
        Machine::new()
    }
}

impl Machine {
    pub fn new() -> Self {
        Machine {
            state: State::Idle,
            is_key_held: false,
            is_v1_running: false,
            mode: TriggerMode::Hold,
            pending_mode: None,
        }
    }

    pub fn state(&self) -> State {
        self.state
    }

    pub fn trigger_mode(&self) -> TriggerMode {
        self.mode
    }

    /// Whether the machine believes the trigger is down. The key adapter
    /// compares it with the live key state to recover a release the event tap
    /// missed.
    pub fn is_key_held(&self) -> bool {
        self.is_key_held
    }

    pub fn handle(&mut self, event: Event) -> Option<Action> {
        let action = self.dispatch(event);
        self.apply_pending_mode();
        action
    }

    fn dispatch(&mut self, event: Event) -> Option<Action> {
        match event {
            Event::TriggerDown(at) => self.on_trigger_down(at),
            Event::TriggerUp(at) => self.on_trigger_up(at),
            Event::Settings(mode) => {
                self.pending_mode = Some(mode);
                None
            }
            Event::OtherKeyDown => self.on_other_key_down(),
            Event::Tick(at) => self.on_tick(at),
            Event::CaptureFailed => self.on_finished(matches!(self.state, State::Recording { .. })),
            Event::Transcribed(text) => self.on_transcribed(text),
            Event::TranscriptionFailed => {
                self.on_finished(matches!(self.state, State::Transcribing { .. }))
            }
            Event::Inserted => self.on_finished(self.state == State::Inserting),
            Event::V1Running(is_running) => self.on_v1_running(is_running),
        }
    }

    fn on_trigger_down(&mut self, at: Instant) -> Option<Action> {
        // The tap can repeat a press while the key is held: only an up→down edge counts.
        if self.is_key_held {
            return None;
        }
        self.is_key_held = true;
        match (self.state, self.mode) {
            (State::Idle, mode) => {
                self.state = State::Recording {
                    mode: match mode {
                        TriggerMode::Hold => Mode::Hold,
                        TriggerMode::Toggle => Mode::Toggle,
                    },
                    pressed_at: at,
                    started_at: at,
                };
                Some(Action::StartCapture)
            }
            // Toggle: the press that stops is the whole gesture.
            (
                State::Recording {
                    mode: Mode::Toggle, ..
                },
                _,
            ) => self.stop_recording(Delivery::Paste),
            _ => None,
        }
    }

    fn on_trigger_up(&mut self, at: Instant) -> Option<Action> {
        if !self.is_key_held {
            return None;
        }
        self.is_key_held = false;
        // Toggle recordings ignore the release (their state is Mode::Toggle).
        let State::Recording {
            mode: Mode::Hold,
            pressed_at,
            ..
        } = self.state
        else {
            return None;
        };
        if at.saturating_duration_since(pressed_at) < MIN_HOLD {
            self.state = self.rest_state();
            return Some(Action::DiscardCapture);
        }
        self.stop_recording(Delivery::Paste)
    }

    /// Only a Hold recording is cancelled by another key: Fn+Delete must not
    /// dictate. V1 never cancels a toggle dictation on a keystroke, and typing
    /// while a hands-free dictation runs is normal, so Toggle keeps recording.
    fn on_other_key_down(&mut self) -> Option<Action> {
        let is_holding = matches!(
            self.state,
            State::Recording {
                mode: Mode::Hold,
                ..
            }
        );
        if !(is_holding && self.is_key_held) {
            return None;
        }
        self.state = self.rest_state();
        Some(Action::DiscardCapture)
    }

    fn on_tick(&mut self, at: Instant) -> Option<Action> {
        let State::Recording { started_at, .. } = self.state else {
            return None;
        };
        if at.saturating_duration_since(started_at) < RECORDING_LIMIT {
            return None;
        }
        self.stop_recording(Delivery::Clipboard)
    }

    fn on_transcribed(&mut self, text: String) -> Option<Action> {
        let State::Transcribing { delivery } = self.state else {
            return None;
        };
        if text.trim().is_empty() {
            self.state = self.rest_state();
            return None;
        }
        self.state = State::Inserting;
        Some(Action::Insert { text, delivery })
    }

    fn on_finished(&mut self, is_expected: bool) -> Option<Action> {
        if is_expected {
            self.state = self.rest_state();
        }
        None
    }

    fn on_v1_running(&mut self, is_running: bool) -> Option<Action> {
        self.is_v1_running = is_running;
        // A dictation already under way finishes; the switch happens at rest.
        match (self.state, is_running) {
            (State::Idle, true) => self.state = State::Yielded,
            (State::Yielded, false) => self.state = State::Idle,
            _ => {}
        }
        None
    }

    fn stop_recording(&mut self, delivery: Delivery) -> Option<Action> {
        self.state = State::Transcribing { delivery };
        Some(Action::StopCaptureAndTranscribe)
    }

    fn apply_pending_mode(&mut self) {
        if matches!(self.state, State::Idle | State::Yielded) {
            if let Some(mode) = self.pending_mode.take() {
                self.mode = mode;
            }
        }
    }

    fn rest_state(&self) -> State {
        if self.is_v1_running {
            State::Yielded
        } else {
            State::Idle
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn later(start: Instant, millis: u64) -> Instant {
        start + Duration::from_millis(millis)
    }

    fn toggle_machine() -> Machine {
        let mut machine = Machine::new();
        machine.handle(Event::Settings(TriggerMode::Toggle));
        machine
    }

    fn insert(text: &str) -> Option<Action> {
        Some(Action::Insert {
            text: text.to_string(),
            delivery: Delivery::Paste,
        })
    }

    #[test]
    fn holding_fn_records_then_release_transcribes_and_inserts() {
        let start = Instant::now();
        let mut machine = Machine::new();
        assert_eq!(
            machine.handle(Event::TriggerDown(start)),
            Some(Action::StartCapture)
        );
        assert_eq!(
            machine.handle(Event::TriggerUp(later(start, 2_000))),
            Some(Action::StopCaptureAndTranscribe)
        );
        assert_eq!(
            machine.handle(Event::Transcribed("bonjour".into())),
            insert("bonjour")
        );
        assert_eq!(machine.state(), State::Inserting);
        assert_eq!(machine.handle(Event::Inserted), None);
        assert_eq!(machine.state(), State::Idle);
    }

    #[test]
    fn a_short_press_in_hold_mode_is_discarded() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        assert_eq!(
            machine.handle(Event::TriggerUp(later(start, 120))),
            Some(Action::DiscardCapture)
        );
        assert_eq!(machine.state(), State::Idle);
    }

    #[test]
    fn toggle_mode_starts_on_one_press_and_stops_on_the_next() {
        let start = Instant::now();
        let mut machine = toggle_machine();
        assert_eq!(
            machine.handle(Event::TriggerDown(start)),
            Some(Action::StartCapture)
        );
        // The release is ignored, however long or short the press was.
        assert_eq!(machine.handle(Event::TriggerUp(later(start, 120))), None);
        assert!(matches!(
            machine.state(),
            State::Recording {
                mode: Mode::Toggle,
                ..
            }
        ));
        assert_eq!(
            machine.handle(Event::TriggerDown(later(start, 9_000))),
            Some(Action::StopCaptureAndTranscribe)
        );
        assert_eq!(machine.handle(Event::TriggerUp(later(start, 9_100))), None);
        assert_eq!(
            machine.state(),
            State::Transcribing {
                delivery: Delivery::Paste
            }
        );
    }

    #[test]
    fn toggle_mode_ignores_a_long_hold_release() {
        let start = Instant::now();
        let mut machine = toggle_machine();
        machine.handle(Event::TriggerDown(start));
        assert_eq!(machine.handle(Event::TriggerUp(later(start, 5_000))), None);
        assert!(matches!(machine.state(), State::Recording { .. }));
    }

    #[test]
    fn the_mode_chosen_mid_dictation_applies_at_the_next_rest() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::Settings(TriggerMode::Toggle));
        assert_eq!(machine.trigger_mode(), TriggerMode::Hold);
        assert_eq!(
            machine.handle(Event::TriggerUp(later(start, 1_000))),
            Some(Action::StopCaptureAndTranscribe)
        );
        machine.handle(Event::Transcribed("x".into()));
        assert_eq!(machine.trigger_mode(), TriggerMode::Hold);
        machine.handle(Event::Inserted);
        assert_eq!(machine.trigger_mode(), TriggerMode::Toggle);
    }

    #[test]
    fn the_default_mode_is_hold_and_idle_applies_a_change_at_once() {
        let mut machine = Machine::new();
        assert_eq!(machine.trigger_mode(), TriggerMode::Hold);
        machine.handle(Event::Settings(TriggerMode::Toggle));
        assert_eq!(machine.trigger_mode(), TriggerMode::Toggle);
    }

    #[test]
    fn a_press_at_exactly_the_tap_limit_is_a_hold() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        let release = start + MIN_HOLD;
        assert_eq!(
            machine.handle(Event::TriggerUp(release)),
            Some(Action::StopCaptureAndTranscribe)
        );
    }

    #[test]
    fn repeated_presses_and_stray_releases_are_ignored() {
        let start = Instant::now();
        let mut machine = Machine::new();
        assert_eq!(machine.handle(Event::TriggerUp(start)), None);
        assert_eq!(machine.state(), State::Idle);
        machine.handle(Event::TriggerDown(start));
        assert_eq!(machine.handle(Event::TriggerDown(later(start, 50))), None);
        assert_eq!(machine.handle(Event::TriggerDown(later(start, 900))), None);
        assert!(matches!(
            machine.state(),
            State::Recording {
                mode: Mode::Hold,
                ..
            }
        ));
    }

    #[test]
    fn fn_as_a_modifier_discards_the_recording() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        assert_eq!(
            machine.handle(Event::OtherKeyDown),
            Some(Action::DiscardCapture)
        );
        assert_eq!(machine.state(), State::Idle);
        // Its release must not start or stop anything.
        assert_eq!(machine.handle(Event::TriggerUp(later(start, 100))), None);
        assert_eq!(machine.state(), State::Idle);
    }

    #[test]
    fn typing_during_a_toggle_recording_keeps_it() {
        let start = Instant::now();
        let mut machine = toggle_machine();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::TriggerUp(later(start, 100)));
        assert_eq!(machine.handle(Event::OtherKeyDown), None);
        assert!(matches!(machine.state(), State::Recording { .. }));
    }

    #[test]
    fn nothing_heard_returns_to_idle_without_inserting() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::TriggerUp(later(start, 1_000)));
        assert_eq!(machine.handle(Event::Transcribed("  ".into())), None);
        assert_eq!(machine.state(), State::Idle);
    }

    #[test]
    fn a_failed_transcription_returns_to_idle() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::TriggerUp(later(start, 1_000)));
        assert_eq!(machine.handle(Event::TranscriptionFailed), None);
        assert_eq!(machine.state(), State::Idle);
    }

    #[test]
    fn fn_is_ignored_while_transcribing_and_inserting() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::TriggerUp(later(start, 1_000)));
        assert_eq!(
            machine.handle(Event::TriggerDown(later(start, 1_100))),
            None
        );
        machine.handle(Event::TriggerUp(later(start, 1_200)));
        machine.handle(Event::Transcribed("texte".into()));
        assert_eq!(
            machine.handle(Event::TriggerDown(later(start, 1_300))),
            None
        );
        assert_eq!(machine.state(), State::Inserting);
    }

    #[test]
    fn the_watchdog_stops_a_forgotten_recording_onto_the_clipboard() {
        let start = Instant::now();
        let mut machine = toggle_machine();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::TriggerUp(later(start, 100)));
        assert_eq!(machine.handle(Event::Tick(later(start, 60_000))), None);
        assert_eq!(
            machine.handle(Event::Tick(start + RECORDING_LIMIT)),
            Some(Action::StopCaptureAndTranscribe)
        );
        assert_eq!(
            machine.handle(Event::Transcribed("long".into())),
            Some(Action::Insert {
                text: "long".into(),
                delivery: Delivery::Clipboard
            })
        );
    }

    #[test]
    fn while_v1_runs_fn_does_nothing() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::V1Running(true));
        assert_eq!(machine.state(), State::Yielded);
        assert_eq!(machine.handle(Event::TriggerDown(start)), None);
        assert_eq!(machine.handle(Event::TriggerUp(later(start, 2_000))), None);
        machine.handle(Event::V1Running(false));
        assert_eq!(machine.state(), State::Idle);
        assert_eq!(
            machine.handle(Event::TriggerDown(later(start, 3_000))),
            Some(Action::StartCapture)
        );
    }

    #[test]
    fn v1_starting_mid_dictation_lets_it_finish_then_yields() {
        let start = Instant::now();
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(start));
        machine.handle(Event::V1Running(true));
        assert_eq!(
            machine.handle(Event::TriggerUp(later(start, 1_000))),
            Some(Action::StopCaptureAndTranscribe)
        );
        machine.handle(Event::Transcribed("fin".into()));
        machine.handle(Event::Inserted);
        assert_eq!(machine.state(), State::Yielded);
    }

    #[test]
    fn a_microphone_that_will_not_open_returns_to_idle() {
        let mut machine = Machine::new();
        machine.handle(Event::TriggerDown(Instant::now()));
        assert_eq!(machine.handle(Event::CaptureFailed), None);
        assert_eq!(machine.state(), State::Idle);
    }

    #[test]
    fn late_results_do_not_move_an_idle_machine() {
        let mut machine = Machine::new();
        assert_eq!(machine.handle(Event::Transcribed("x".into())), None);
        assert_eq!(machine.handle(Event::Inserted), None);
        assert_eq!(machine.handle(Event::TranscriptionFailed), None);
        assert_eq!(machine.state(), State::Idle);
    }
}

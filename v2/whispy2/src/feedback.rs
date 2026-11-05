//! What the user sees and hears while dictating, behind a port.
//!
//! The controller drives it from the machine's state; the macOS adapter is a
//! floating panel, a Linux one can be a tray icon or a notification. The trait
//! is `Send` and takes `&mut self` so the controller thread owns it: an
//! adapter that touches the UI hops to its main thread inside each call (as
//! `menu_bar::show` does) instead of the controller knowing about threads.

use std::time::{Duration, Instant};

use crate::machine::State;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Recording,
    Transcribing,
    Hidden,
}

pub trait Feedback: Send {
    /// The indicator to show, or hide. Called on changes only.
    fn show(&mut self, phase: Phase);
    /// The input level of the current recording, 0.0 to 1.0, about 20 times a second.
    fn level(&mut self, level: f32);
    /// Something went wrong that the menu bar icon alone would not get noticed: a sound.
    fn alert(&mut self);
}

/// Shows nothing: the default until an adapter exists, and the Linux stub.
pub struct NoFeedback;

impl Feedback for NoFeedback {
    fn show(&mut self, _phase: Phase) {}
    fn level(&mut self, _level: f32) {}
    fn alert(&mut self) {}
}

/// Inserting is the tail of transcribing for the user: the panel stays until the text is in.
pub fn phase_of(state: State) -> Phase {
    match state {
        State::Recording { .. } => Phase::Recording,
        State::Transcribing { .. } | State::Inserting => Phase::Transcribing,
        State::Idle | State::Yielded => Phase::Hidden,
    }
}

/// Level updates are pushed at most this often: a UI does not need one per audio block.
pub const LEVEL_PERIOD: Duration = Duration::from_millis(50);

/// Lets one block in [`LEVEL_PERIOD`] through (20 Hz).
pub struct LevelThrottle {
    last: Option<Instant>,
}

impl LevelThrottle {
    pub fn new() -> Self {
        LevelThrottle { last: None }
    }

    pub fn is_due(&mut self, now: Instant) -> bool {
        let due = self
            .last
            .is_none_or(|last| now.saturating_duration_since(last) >= LEVEL_PERIOD);
        if due {
            self.last = Some(now);
        }
        due
    }
}

impl Default for LevelThrottle {
    fn default() -> Self {
        LevelThrottle::new()
    }
}

/// Root mean square of one audio block; 0.0 for an empty one.
pub fn block_rms(samples: impl IntoIterator<Item = f32>) -> f32 {
    let (sum, count) = samples
        .into_iter()
        .fold((0.0f32, 0u32), |(sum, count), sample| {
            (sum + sample * sample, count + 1)
        });
    if count == 0 {
        0.0
    } else {
        (sum / count as f32).sqrt()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::machine::{Delivery, Mode};

    #[test]
    fn the_panel_stays_up_from_recording_until_the_text_is_inserted() {
        let now = Instant::now();
        let recording = State::Recording {
            mode: Mode::Hold,
            pressed_at: now,
            started_at: now,
        };
        assert_eq!(phase_of(recording), Phase::Recording);
        let transcribing = State::Transcribing {
            delivery: Delivery::Paste,
        };
        assert_eq!(phase_of(transcribing), Phase::Transcribing);
        assert_eq!(phase_of(State::Inserting), Phase::Transcribing);
        assert_eq!(phase_of(State::Idle), Phase::Hidden);
        assert_eq!(phase_of(State::Yielded), Phase::Hidden);
    }

    #[test]
    fn levels_pass_at_twenty_hertz() {
        let start = Instant::now();
        let mut throttle = LevelThrottle::new();
        assert!(throttle.is_due(start));
        assert!(!throttle.is_due(start + Duration::from_millis(10)));
        assert!(!throttle.is_due(start + Duration::from_millis(49)));
        assert!(throttle.is_due(start + Duration::from_millis(50)));
        assert!(!throttle.is_due(start + Duration::from_millis(60)));
    }

    #[test]
    fn rms_of_a_block() {
        assert_eq!(block_rms([]), 0.0);
        assert!((block_rms([0.5, -0.5, 0.5, -0.5]) - 0.5).abs() < 1e-6);
    }
}

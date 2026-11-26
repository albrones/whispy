//! The trigger key under X11: Right Ctrl, V1's Linux default.
//!
//! XInput 2 raw key events, selected on the root window: every key press and
//! release reaches V2 whichever window has the focus, nothing is grabbed, so
//! the key keeps working everywhere else (pynput's record listener sees the
//! same thing in V1). A failure to listen is an `Err` with a sentence for the
//! user, never a panic: Whispy keeps running and the socket still drives it.

use std::thread;
use std::time::Instant;

use x11rb::connection::{Connection, RequestConnection};
use x11rb::protocol::xinput::{self, ConnectionExt as _, KeyEventFlags, XIEventMask};
use x11rb::protocol::xproto::ConnectionExt as _;
use x11rb::protocol::Event as XEvent;

use crate::machine::Event;

/// `XK_Control_R`.
pub const TRIGGER_KEYSYM: u32 = 0xffe4;
/// The key's name, as the user reads it.
pub const TRIGGER_NAME: &str = "Right Ctrl";

/// What the user is told when the key cannot be listened to.
pub fn unavailable(reason: &str) -> String {
    format!(
        "Whispy cannot listen to the {TRIGGER_NAME} key: {reason}. Whispy keeps running; \
         dictation can still be started through its control socket."
    )
}

/// Turns raw key events into the machine's events. Pure: the X connection
/// only feeds it.
#[derive(Debug)]
pub struct Decoder {
    triggers: Vec<u32>,
    held: bool,
}

impl Decoder {
    /// `triggers`: every keycode the trigger keysym is on.
    pub fn new(triggers: Vec<u32>) -> Decoder {
        Decoder {
            triggers,
            held: false,
        }
    }

    /// A key went down. An autorepeat of the held trigger is not a new press;
    /// another key while the trigger is held makes it a modifier (Right Ctrl+C).
    pub fn press(&mut self, keycode: u32, repeat: bool, now: Instant) -> Option<Event> {
        if self.triggers.contains(&keycode) {
            if self.held || repeat {
                return None;
            }
            self.held = true;
            return Some(Event::TriggerDown(now));
        }
        (self.held && !repeat).then_some(Event::OtherKeyDown)
    }

    pub fn release(&mut self, keycode: u32, now: Instant) -> Option<Event> {
        if !self.triggers.contains(&keycode) || !self.held {
            return None;
        }
        self.held = false;
        Some(Event::TriggerUp(now))
    }
}

/// The keycodes whose keysym list holds `keysym`, from a `GetKeyboardMapping`
/// reply that starts at `min_keycode`.
pub fn keycodes_for(keysym: u32, min_keycode: u8, per_keycode: u8, keysyms: &[u32]) -> Vec<u32> {
    if per_keycode == 0 {
        return Vec::new();
    }
    keysyms
        .chunks(per_keycode as usize)
        .enumerate()
        .filter(|(_, row)| row.contains(&keysym))
        .map(|(index, _)| u32::from(min_keycode) + index as u32)
        .collect()
}

/// Listens on its own thread until the X connection ends. `on_event` gets the
/// machine's events; `on_lost` gets the sentence for the user if the
/// connection breaks later.
pub fn listen(
    on_event: impl Fn(Event) + Send + 'static,
    on_lost: impl FnOnce(String) + Send + 'static,
) -> Result<(), String> {
    let (connection, screen) = x11rb::connect(None)
        .map_err(|error| unavailable(&format!("the X server is unreachable ({error})")))?;
    let fail =
        |what: &str, error: &dyn std::fmt::Display| unavailable(&format!("{what} ({error})"));
    if connection
        .extension_information(xinput::X11_EXTENSION_NAME)
        .map_err(|error| fail("the X server did not answer", &error))?
        .is_none()
    {
        return Err(unavailable("the X server has no XInput extension"));
    }
    let version = connection
        .xinput_xi_query_version(2, 2)
        .map_err(|error| fail("the X server did not answer", &error))?
        .reply()
        .map_err(|error| fail("XInput 2 is not available", &error))?;
    if version.major_version < 2 {
        return Err(unavailable("the X server has XInput 1 only, not XInput 2"));
    }
    let setup = connection.setup();
    let root = setup.roots[screen].root;
    let (min, max) = (setup.min_keycode, setup.max_keycode);
    let mapping = connection
        .get_keyboard_mapping(min, max - min + 1)
        .map_err(|error| fail("the keyboard map could not be read", &error))?
        .reply()
        .map_err(|error| fail("the keyboard map could not be read", &error))?;
    let triggers = keycodes_for(
        TRIGGER_KEYSYM,
        min,
        mapping.keysyms_per_keycode,
        &mapping.keysyms,
    );
    if triggers.is_empty() {
        return Err(unavailable(&format!(
            "no key of this keyboard layout is {TRIGGER_NAME}"
        )));
    }
    connection
        .xinput_xi_select_events(
            root,
            &[xinput::EventMask {
                deviceid: xinput::Device::ALL_MASTER.into(),
                mask: vec![XIEventMask::RAW_KEY_PRESS | XIEventMask::RAW_KEY_RELEASE],
            }],
        )
        .map_err(|error| fail("the key events could not be selected", &error))?
        .check()
        .map_err(|error| fail("the key events could not be selected", &error))?;
    crate::log::line(&format!(
        "X11 trigger: {TRIGGER_NAME} (keycodes {triggers:?}), XInput {}.{}",
        version.major_version, version.minor_version
    ));
    let mut decoder = Decoder::new(triggers);
    thread::Builder::new()
        .name("whispy2-x11-trigger".into())
        .spawn(move || loop {
            let event = match connection.wait_for_event() {
                Ok(event) => event,
                Err(error) => {
                    on_lost(unavailable(&format!("the X connection was lost ({error})")));
                    return;
                }
            };
            let now = Instant::now();
            let edge = match event {
                XEvent::XinputRawKeyPress(key) => decoder.press(
                    key.detail,
                    key.flags.contains(KeyEventFlags::KEY_REPEAT),
                    now,
                ),
                XEvent::XinputRawKeyRelease(key) => decoder.release(key.detail, now),
                _ => None,
            };
            if let Some(edge) = edge {
                on_event(edge);
            }
        })
        .map_err(|error| unavailable(&format!("its thread could not start ({error})")))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const RIGHT_CTRL: u32 = 105;
    const C: u32 = 54;

    fn is_down(event: Option<Event>) -> bool {
        matches!(event, Some(Event::TriggerDown(_)))
    }

    #[test]
    fn a_press_and_its_release_are_one_dictation() {
        let mut decoder = Decoder::new(vec![RIGHT_CTRL]);
        let now = Instant::now();
        assert!(is_down(decoder.press(RIGHT_CTRL, false, now)));
        assert!(matches!(
            decoder.release(RIGHT_CTRL, now),
            Some(Event::TriggerUp(_))
        ));
        assert_eq!(decoder.release(RIGHT_CTRL, now), None);
    }

    #[test]
    fn autorepeat_and_a_second_press_while_held_are_ignored() {
        let mut decoder = Decoder::new(vec![RIGHT_CTRL]);
        let now = Instant::now();
        assert_eq!(decoder.press(RIGHT_CTRL, true, now), None);
        assert!(is_down(decoder.press(RIGHT_CTRL, false, now)));
        assert_eq!(decoder.press(RIGHT_CTRL, false, now), None);
        assert_eq!(decoder.press(RIGHT_CTRL, true, now), None);
    }

    #[test]
    fn another_key_while_held_makes_it_a_shortcut() {
        let mut decoder = Decoder::new(vec![RIGHT_CTRL]);
        let now = Instant::now();
        assert_eq!(decoder.press(C, false, now), None);
        decoder.press(RIGHT_CTRL, false, now);
        assert_eq!(decoder.press(C, false, now), Some(Event::OtherKeyDown));
        assert_eq!(decoder.release(C, now), None);
    }

    #[test]
    fn the_keycodes_of_a_keysym_are_found_in_the_map() {
        // Two keysyms per keycode, from keycode 8.
        let map = [0x61, 0x41, TRIGGER_KEYSYM, 0, 0x62, 0x42, 0, TRIGGER_KEYSYM];
        assert_eq!(keycodes_for(TRIGGER_KEYSYM, 8, 2, &map), vec![9, 11]);
        assert_eq!(keycodes_for(0xffe3, 8, 2, &map), Vec::<u32>::new());
        assert_eq!(keycodes_for(TRIGGER_KEYSYM, 8, 0, &map), Vec::<u32>::new());
    }

    #[test]
    fn the_message_names_the_key_and_the_way_out() {
        let message = unavailable("the X server is unreachable");
        assert!(message.contains("Right Ctrl"));
        assert!(message.contains("keeps running"));
    }
}

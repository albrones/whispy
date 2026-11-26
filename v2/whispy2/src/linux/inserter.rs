//! Puts the text where the user is, through enigo: XTest under X11, the
//! virtual-keyboard protocol under Wayland (Hyprland, sway).
//!
//! The text is always typed, as the cadrage chose: « Copy to clipboard » is a
//! macOS paste and is not honoured here. Only the watchdog's
//! [`Delivery::Clipboard`] touches the clipboard, through `wl-copy` (Wayland)
//! or `xclip` / `xsel` (X11), the tools V1 uses.
//!
//! enigo connects to every backend it is built with and types through each one
//! that answers: under Wayland, XWayland's `DISPLAY` would type the text twice.
//! So the backend of the other session is given a display name that cannot
//! connect ([`enigo_settings`]).
//!
//! The text goes one key at a time ([`keys`]), never through `Enigo::text`:
//! under Wayland that commits it through the input-method protocol, which only
//! reaches an app with an active text-input field (a terminal gets nothing, and
//! enigo reports success). Keys go through the virtual keyboard, as `wtype`.

use std::io::Write;
use std::process::{Command, Stdio};

use enigo::{Direction, Enigo, Key, Keyboard, Settings};

use super::session::Session;
use crate::controller::Inserter;
use crate::machine::Delivery;

/// A display name no X server or Wayland compositor answers to: no `:` for
/// X11 (it fails to parse, nothing is opened), no such socket for Wayland.
const NO_DISPLAY: &str = "whispy-not-this-session";

pub struct EnigoInserter {
    session: Session,
}

impl EnigoInserter {
    pub fn new(session: Session) -> EnigoInserter {
        EnigoInserter { session }
    }
}

/// enigo's settings for `session`: only that session's backend can connect.
pub fn enigo_settings(session: Session) -> Settings {
    let mut settings = Settings::default();
    match session {
        Session::Wayland => settings.x11_display = Some(NO_DISPLAY.to_string()),
        Session::X11 => settings.wayland_display = Some(NO_DISPLAY.to_string()),
        Session::None => {}
    }
    settings
}

impl Inserter for EnigoInserter {
    fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String> {
        if delivery == Delivery::Clipboard {
            return copy(self.session, text);
        }
        // A fresh connection per delivery: enigo's is not `Send`, and a
        // compositor or X server restarted since the last one is picked up.
        let mut enigo = Enigo::new(&enigo_settings(self.session)).map_err(|error| {
            format!(
                "the text could not be typed: no {} input connection ({error})",
                self.session.name()
            )
        })?;
        for key in keys(text) {
            enigo
                .key(key, Direction::Click)
                .map_err(|error| format!("the text could not be typed ({error})"))?;
        }
        Ok(())
    }
}

/// The keys that type `text`: a line break is Return, a tab is Tab, any other
/// character its own key (enigo maps it to a free keycode when the layout lacks it).
pub fn keys(text: &str) -> impl Iterator<Item = Key> + '_ {
    text.chars().filter(|c| *c != '\r').map(|c| match c {
        '\n' => Key::Return,
        '\t' => Key::Tab,
        other => Key::Unicode(other),
    })
}

/// The clipboard commands to try for `session`, in order.
pub fn copy_commands(session: Session) -> &'static [&'static [&'static str]] {
    match session {
        Session::Wayland => &[&["wl-copy"]],
        Session::X11 | Session::None => &[
            &["xclip", "-selection", "clipboard"],
            &["xsel", "--clipboard", "--input"],
        ],
    }
}

fn copy(session: Session, text: &str) -> Result<(), String> {
    let mut last_error = String::new();
    for command in copy_commands(session) {
        let child = Command::new(command[0])
            .args(&command[1..])
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn();
        let mut child = match child {
            Ok(child) => child,
            Err(error) => {
                last_error = format!("{}: {error}", command[0]);
                continue;
            }
        };
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        // The tool forks a server for the selection and exits: reaped off this thread.
        std::thread::spawn(move || {
            let _ = child.wait();
        });
        return Ok(());
    }
    Err(format!(
        "the text could not be put on the clipboard ({last_error})"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_sessions_own_backend_can_connect() {
        let wayland = enigo_settings(Session::Wayland);
        assert_eq!(wayland.x11_display.as_deref(), Some(NO_DISPLAY));
        assert_eq!(wayland.wayland_display, None);
        let x11 = enigo_settings(Session::X11);
        assert_eq!(x11.wayland_display.as_deref(), Some(NO_DISPLAY));
        assert_eq!(x11.x11_display, None);
        assert!(!NO_DISPLAY.contains(':'));
    }

    #[test]
    fn each_character_is_one_key_and_line_breaks_are_return() {
        let keys: Vec<Key> = keys("é 3\r\n\t").collect();
        assert_eq!(
            keys,
            [
                Key::Unicode('é'),
                Key::Unicode(' '),
                Key::Unicode('3'),
                Key::Return,
                Key::Tab
            ]
        );
    }

    #[test]
    fn the_clipboard_tool_follows_the_session() {
        assert_eq!(copy_commands(Session::Wayland)[0][0], "wl-copy");
        assert_eq!(copy_commands(Session::X11)[0][0], "xclip");
    }
}

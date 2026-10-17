//! Text into the frontmost app, the way V1 does it (`hardware/injection.py`):
//! the text goes on the clipboard, `osascript` has System Events press ⌘V,
//! then the previous clipboard is put back.
//!
//! System Events is Apple-signed, so it may post the keystroke when the app
//! that launched whispy2 has Accessibility; the text itself is data on
//! `pbcopy`'s stdin, never part of a script.

use std::io::Write;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

use crate::controller::Inserter;
use crate::machine::Delivery;

const PASTE_SCRIPT: &str =
    r#"tell application "System Events" to keystroke "v" using command down"#;
/// The Apple-event error when System Events may not type (errAEEventNotPermitted);
/// matched by number, the message is localised.
const KEYSTROKE_NOT_PERMITTED: &str = "1002";
/// Time for the target app to read the pasted text before the clipboard is restored.
const CLIPBOARD_RESTORE_DELAY: Duration = Duration::from_millis(150);

pub struct PasteInserter;

impl Inserter for PasteInserter {
    fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String> {
        if delivery == Delivery::Clipboard {
            return copy(text.as_bytes());
        }
        // ponytail: plain text only — rich text or an image on the clipboard
        // comes back as its plain-text form, or not at all (as in V1).
        let previous = paste_board()?;
        copy(text.as_bytes())?;
        let pasted = Command::new("osascript")
            .args(["-e", PASTE_SCRIPT])
            .output()
            .map_err(|error| format!("osascript could not run: {error}"))?;
        if !pasted.status.success() {
            let detail = String::from_utf8_lossy(&pasted.stderr).trim().to_string();
            // The text stays on the clipboard, for the user to paste by hand.
            if detail.contains(KEYSTROKE_NOT_PERMITTED) {
                return Err(format!(
                    "macOS refused the paste: grant Accessibility to the app that launched \
                     whispy2 (System Settings → Privacy & Security → Accessibility). \
                     The text is on the clipboard. ({detail})"
                ));
            }
            return Err(format!(
                "the paste failed; the text is on the clipboard. ({detail})"
            ));
        }
        thread::sleep(CLIPBOARD_RESTORE_DELAY);
        copy(&previous)
    }
}

/// `pbcopy` and `pbpaste` decode through the locale; a process started from
/// launchd or Finder has none and falls back to Mac Roman (V1: « ç » became « √ß »).
fn utf8(command: &mut Command) -> &mut Command {
    command
        .env("LC_ALL", "en_US.UTF-8")
        .env("LANG", "en_US.UTF-8")
}

fn copy(bytes: &[u8]) -> Result<(), String> {
    let mut child = utf8(&mut Command::new("pbcopy"))
        .stdin(Stdio::piped())
        .spawn()
        .map_err(|error| format!("pbcopy could not run: {error}"))?;
    child
        .stdin
        .take()
        .expect("pbcopy's stdin is piped")
        .write_all(bytes)
        .map_err(|error| format!("writing to pbcopy: {error}"))?;
    let status = child.wait().map_err(|error| format!("pbcopy: {error}"))?;
    if !status.success() {
        return Err(format!("pbcopy exited with {status}"));
    }
    Ok(())
}

fn paste_board() -> Result<Vec<u8>, String> {
    let output = utf8(&mut Command::new("pbpaste"))
        .output()
        .map_err(|error| format!("pbpaste could not run: {error}"))?;
    Ok(output.stdout)
}

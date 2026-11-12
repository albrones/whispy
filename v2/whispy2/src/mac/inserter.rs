//! Text into the frontmost app, the way V1 does it (`hardware/injection.py`):
//! the text goes on the clipboard, `osascript` has System Events press ⌘V,
//! then the previous clipboard is put back.
//!
//! System Events is Apple-signed, so it may post the keystroke when the app
//! that launched whispy2 has Accessibility; the text itself is data on
//! `pbcopy`'s stdin, never part of a script.
//!
//! With "Copy to clipboard" off (V1's `copy_to_clipboard: false`) the text is
//! typed instead, by `keystroke`, and the clipboard is not touched. The text
//! then goes to `osascript` as an argument the script reads as data: a quote in
//! a dictation cannot end a string literal and run what follows.

use std::io::Write;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
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

/// Delivers through the clipboard or, when `typed` is set, by typing. `typed`
/// is shared so the menu can flip it for the next dictation without a restart.
pub struct PasteInserter {
    typed: Arc<AtomicBool>,
}

impl PasteInserter {
    pub fn new(typed: Arc<AtomicBool>) -> PasteInserter {
        PasteInserter { typed }
    }
}

/// The `osascript` arguments that type `text`: the script is fixed and reads the
/// text from its argument list, so the text is never part of the source.
/// `--` ends osascript's own options, for a text that starts with `-`.
pub fn type_command_args(text: &str) -> Vec<String> {
    [
        "-e",
        "on run argv",
        "-e",
        r#"tell application "System Events" to keystroke (item 1 of argv)"#,
        "-e",
        "end run",
        "--",
        text,
    ]
    .into_iter()
    .map(str::to_string)
    .collect()
}

fn accessibility_refused(what: &str, detail: &str, tail: &str) -> String {
    format!(
        "macOS refused the {what}: grant Accessibility to Whispy V2 (or to the \
         terminal that launched whispy2) (System Settings → Privacy & Security → Accessibility). \
         {tail}({detail})"
    )
}

/// Starts System Events and passes macOS's Apple-event check ahead of the
/// first paste. Cold, the first paste after a launch took 4.6 s against
/// 0.5–0.6 s after it (2026-11-04): with a launch per login, that one slow
/// dictation a day was enough to break the trial's latency p95. Runs on its
/// own thread; a failure here shows again, with its message, at the paste.
pub fn warm_up() {
    let spawned = thread::Builder::new()
        .name("whispy2-paste-warm-up".into())
        .spawn(|| {
            let _ = Command::new("osascript")
                .args(["-e", r#"tell application "System Events" to get name"#])
                .output();
        });
    if let Err(error) = spawned {
        crate::log::line(&format!("paste warm-up not started: {error}"));
    }
}

impl Inserter for PasteInserter {
    fn deliver(&mut self, text: &str, delivery: Delivery) -> Result<(), String> {
        if delivery == Delivery::Clipboard {
            return copy(text.as_bytes());
        }
        if self.typed.load(Ordering::Relaxed) {
            return type_text(text);
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
                return Err(accessibility_refused(
                    "paste",
                    &detail,
                    "The text is on the clipboard. ",
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

/// Types `text` into the frontmost app; the clipboard is left alone.
fn type_text(text: &str) -> Result<(), String> {
    if text.is_empty() {
        return Ok(());
    }
    let typed = utf8(&mut Command::new("osascript"))
        .args(type_command_args(text))
        .output()
        .map_err(|error| format!("osascript could not run: {error}"))?;
    if typed.status.success() {
        return Ok(());
    }
    let detail = String::from_utf8_lossy(&typed.stderr).trim().to_string();
    if detail.contains(KEYSTROKE_NOT_PERMITTED) {
        return Err(accessibility_refused("typing", &detail, ""));
    }
    Err(format!("typing the text failed. ({detail})"))
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_text_is_the_last_argument_and_the_script_is_fixed() {
        let args = type_command_args("bonjour");
        assert_eq!(args.last().map(String::as_str), Some("bonjour"));
        assert_eq!(args[args.len() - 2], "--");
        let scripts: Vec<&str> = args
            .iter()
            .zip(args.iter().skip(1))
            .filter(|(flag, _)| *flag == "-e")
            .map(|(_, script)| script.as_str())
            .collect();
        assert_eq!(
            scripts,
            [
                "on run argv",
                r#"tell application "System Events" to keystroke (item 1 of argv)"#,
                "end run"
            ]
        );
    }

    #[test]
    fn quotes_cannot_break_out_of_the_script() {
        let hostile = r#"" & do shell script "touch /tmp/x"#;
        let args = type_command_args(hostile);
        let occurrences = args.iter().filter(|arg| arg.contains(hostile)).count();
        assert_eq!(occurrences, 1);
        // The one element that holds it is the argv item, never a `-e` script.
        let at = args.iter().position(|arg| arg == hostile).unwrap();
        assert_eq!(at, args.len() - 1);
        assert_ne!(args[at - 1], "-e");
        assert!(args
            .iter()
            .take(args.len() - 1)
            .all(|arg| !arg.contains("do shell script")));
    }

    #[test]
    fn a_leading_dash_stays_text() {
        let args = type_command_args("-e say hi");
        assert_eq!(args[args.len() - 2], "--");
        assert_eq!(args.last().map(String::as_str), Some("-e say hi"));
    }

    #[test]
    fn the_typed_switch_is_shared() {
        let typed = Arc::new(AtomicBool::new(false));
        let inserter = PasteInserter::new(Arc::clone(&typed));
        typed.store(true, Ordering::Relaxed);
        assert!(inserter.typed.load(Ordering::Relaxed));
    }
}

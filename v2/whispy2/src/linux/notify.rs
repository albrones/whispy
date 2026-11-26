//! V1's alerts as desktop notifications, through `notify-send` (libnotify),
//! as V1 does under Linux: no D-Bus client of our own for a one-way message.

use std::process::{Command, Stdio};

use crate::log;
use crate::menu_model::Alert;

/// The `notify-send` arguments for `alert`: title « Whispy — <subtitle> », the
/// message as the body. The text comes after `--`, so it is never an option.
pub fn arguments(alert: &Alert) -> Vec<String> {
    vec![
        "--app-name=Whispy".to_string(),
        "--".to_string(),
        format!("Whispy — {}", alert.subtitle),
        alert.message.clone(),
    ]
}

/// Posts `alert` now. Any thread; returns at once (the child is not waited for
/// beyond its spawn, and is reaped by a short-lived thread).
pub fn post(alert: &Alert) {
    let spawned = Command::new("notify-send")
        .args(arguments(alert))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    match spawned {
        Ok(mut child) => {
            std::thread::spawn(move || {
                let _ = child.wait();
            });
        }
        Err(error) => log::line(&format!(
            "notification not shown (notify-send: {error}); install libnotify: {}: {}",
            alert.subtitle, alert.message
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_text_follows_the_end_of_options() {
        let alert = Alert::dictation_stopped("--version");
        let args = arguments(&alert);
        assert_eq!(args[1], "--");
        assert_eq!(args[2], "Whispy — Dictation stopped");
        assert_eq!(args[3], "--version");
    }
}

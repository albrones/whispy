//! What the user sees under Linux: the tray icon when there is one (X11), and
//! notifications for alerts in every session.

use ksni::blocking::Handle;

use super::notify;
use super::tray::WhispyTray;
use crate::controller::Status;
use crate::feedback::{Feedback, Phase};
use crate::menu_model::Alert;
use crate::update::Row;

/// A handle on the icon, if it started. Cloned into the controller (feedback)
/// and the status callback.
#[derive(Clone, Default)]
pub struct Surface {
    tray: Option<Handle<WhispyTray>>,
}

impl Surface {
    pub fn new(tray: Option<Handle<WhispyTray>>) -> Surface {
        Surface { tray }
    }

    /// The status line in the icon's menu and tooltip: the last problem, else the headline.
    pub fn status(&self, status: &Status) {
        let line = status
            .last_problem()
            .map(str::to_string)
            .unwrap_or_else(|| status.headline().to_string());
        if let Some(tray) = &self.tray {
            tray.update(|tray| tray.status = line);
        }
    }
}

impl Surface {
    /// The update row in the icon's menu.
    pub fn update_row(&self, row: Option<&Row>) {
        if let Some(tray) = &self.tray {
            let row = row.cloned();
            tray.update(|tray| tray.update = row);
        }
    }
}

impl Feedback for Surface {
    fn show(&mut self, phase: Phase) {
        if let Some(tray) = &self.tray {
            tray.update(|tray| tray.listening = phase == Phase::Recording);
        }
    }

    fn level(&mut self, _level: f32) {}

    fn alert(&mut self, alert: Alert) {
        notify::post(&alert);
    }
}

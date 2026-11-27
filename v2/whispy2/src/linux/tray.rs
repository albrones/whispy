//! The X11 tray icon (StatusNotifierItem): the state at a glance (a grey ring
//! at rest, a red dot while listening), the status line, the update row
//! (« Update available (X.Y.Z) », only when there is one) and Quit.
//!
//! V1's rule holds: an icon is decoration and must never stop dictation. When
//! it cannot start (no D-Bus session, no tray host in the panel) the caller
//! logs why and posts one notification, and Whispy runs without it.

use std::sync::mpsc::Sender;

use ksni::blocking::{Handle, TrayMethods};
use ksni::menu::StandardItem;
use ksni::{Icon, MenuItem, ToolTip};

use crate::log;
use crate::update::{Row, Updater};

/// The icon's side, in pixels: panels scale it, 22 is the usual tray size.
pub const ICON_SIZE: i32 = 22;

/// Rest: a grey ring. Listening: a red dot.
const REST_RGB: [u8; 3] = [0x9e, 0x9e, 0x9e];
const LISTENING_RGB: [u8; 3] = [0xe5, 0x39, 0x35];

pub struct WhispyTray {
    pub listening: bool,
    /// The status line (« Ready — hold the trigger key to dictate », a problem).
    pub status: String,
    /// The update row, as the updater last reported it; `None`: up to date.
    pub update: Option<Row>,
    updater: Updater,
    quit: Sender<()>,
}

impl WhispyTray {
    pub fn new(quit: Sender<()>, updater: Updater) -> WhispyTray {
        WhispyTray {
            listening: false,
            status: crate::controller::LOADING_NOTE.to_string(),
            update: updater.row(),
            updater,
            quit,
        }
    }
}

/// The icon for a state, ARGB32 in network byte order as the specification asks.
pub fn icon(listening: bool) -> Icon {
    let size = ICON_SIZE;
    let center = (size as f32 - 1.0) / 2.0;
    let outer = size as f32 / 2.0 - 2.0;
    let inner = outer - 3.0;
    let [r, g, b] = if listening { LISTENING_RGB } else { REST_RGB };
    let mut data = Vec::with_capacity((size * size * 4) as usize);
    for y in 0..size {
        for x in 0..size {
            let distance = ((x as f32 - center).powi(2) + (y as f32 - center).powi(2)).sqrt();
            let inside = distance <= outer && (listening || distance >= inner);
            data.extend_from_slice(&if inside {
                [0xff, r, g, b]
            } else {
                [0, 0, 0, 0]
            });
        }
    }
    Icon {
        width: size,
        height: size,
        data,
    }
}

impl ksni::Tray for WhispyTray {
    fn id(&self) -> String {
        "whispy".into()
    }

    fn title(&self) -> String {
        "Whispy".into()
    }

    fn icon_pixmap(&self) -> Vec<Icon> {
        vec![icon(self.listening)]
    }

    fn tool_tip(&self) -> ToolTip {
        ToolTip {
            title: "Whispy".into(),
            description: self.status.clone(),
            ..Default::default()
        }
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        let mut items = vec![
            StandardItem {
                label: self.status.clone(),
                enabled: false,
                ..Default::default()
            }
            .into(),
            MenuItem::Separator,
        ];
        if let Some(update) = &self.update {
            items.push(
                StandardItem {
                    label: update.title.clone(),
                    enabled: update.enabled,
                    activate: Box::new(|tray: &mut Self| {
                        tray.updater.install();
                    }),
                    ..Default::default()
                }
                .into(),
            );
        }
        items.push(
            StandardItem {
                label: "Quit".into(),
                activate: Box::new(|tray: &mut Self| {
                    let _ = tray.quit.send(());
                }),
                ..Default::default()
            }
            .into(),
        );
        items
    }

    fn watcher_offline(&self, reason: ksni::OfflineReason) -> bool {
        // The panel went away: keep the service, it comes back with the panel.
        log::line(&format!(
            "tray icon: the tray host went offline ({reason:?})"
        ));
        true
    }
}

/// Starts the icon. `Err` says why it cannot be shown.
pub fn spawn(quit: Sender<()>, updater: Updater) -> Result<Handle<WhispyTray>, String> {
    WhispyTray::new(quit, updater)
        .spawn()
        .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pixel(icon: &Icon, x: i32, y: i32) -> [u8; 4] {
        let at = ((y * icon.width + x) * 4) as usize;
        icon.data[at..at + 4].try_into().unwrap()
    }

    #[test]
    fn rest_is_a_grey_ring_and_listening_a_red_dot() {
        let rest = icon(false);
        let listening = icon(true);
        assert_eq!(rest.data.len(), (ICON_SIZE * ICON_SIZE * 4) as usize);
        let middle = ICON_SIZE / 2;
        assert_eq!(pixel(&rest, middle, middle), [0, 0, 0, 0]);
        assert_eq!(pixel(&rest, middle, 2), [0xff, 0x9e, 0x9e, 0x9e]);
        assert_eq!(pixel(&listening, middle, middle), [0xff, 0xe5, 0x39, 0x35]);
        assert_eq!(pixel(&listening, 0, 0), [0, 0, 0, 0]);
    }

    fn test_updater() -> Updater {
        use crate::update::{Checked, Installed, Version};
        Updater::with(
            Version(2, 4, 0),
            || Checked::Latest(Version(2, 5, 0)),
            |_| Installed::Done,
        )
    }

    fn labels(tray: &WhispyTray) -> Vec<String> {
        ksni::Tray::menu(tray)
            .iter()
            .filter_map(|item| match item {
                MenuItem::Standard(item) => Some(item.label.clone()),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn up_to_date_the_menu_shows_the_status_and_quit_reaches_the_app() {
        let (quit, quitted) = std::sync::mpsc::channel();
        let mut tray = WhispyTray::new(quit, test_updater());
        tray.status = "Ready".into();
        assert_eq!(labels(&tray), ["Ready", "Quit"]);
        let menu = ksni::Tray::menu(&tray);
        if let MenuItem::Standard(quit_item) = &menu[2] {
            (quit_item.activate)(&mut tray);
        }
        assert!(quitted.try_recv().is_ok());
    }

    #[test]
    fn an_offered_update_shows_and_installs_on_its_own_click() {
        let (quit, _quitted) = std::sync::mpsc::channel();
        let updater = test_updater();
        let mut tray = WhispyTray::new(quit, updater.clone());
        updater.check();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while updater.row().is_none() {
            assert!(std::time::Instant::now() < deadline, "no offer");
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        tray.update = updater.row();
        tray.status = "Ready".into();
        assert_eq!(labels(&tray), ["Ready", "Update available (2.5.0)", "Quit"]);
        let menu = ksni::Tray::menu(&tray);
        let MenuItem::Standard(item) = &menu[2] else {
            panic!("the update item is a standard item")
        };
        assert!(item.enabled);
        (item.activate)(&mut tray);
        // The fake install ends without a restart: the row says so (#50).
        while updater.row().is_none_or(|row| row.transient || row.enabled) {
            assert!(std::time::Instant::now() < deadline, "{:?}", updater.row());
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        assert_eq!(
            updater.row().unwrap().title,
            "2.5.0 is installed \u{2014} quit and reopen Whispy to finish"
        );
    }
}

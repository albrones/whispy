//! The X11 tray icon (StatusNotifierItem): the state at a glance (a grey ring
//! at rest, a red dot while listening), the status line, the update row
//! (« Update available (X.Y.Z) », only when there is one), « Language: … »
//! and Quit. Every label is drawn in the language in force when the host
//! asks for the menu, so a language choice shows at once.
//!
//! V1's rule holds: an icon is decoration and must never stop dictation. When
//! it cannot start (no D-Bus session, no tray host in the panel) the caller
//! logs why and posts one notification, and Whispy runs without it.

use std::path::PathBuf;
use std::sync::mpsc::Sender;

use ksni::blocking::{Handle, TrayMethods};
use ksni::menu::{RadioGroup, RadioItem, StandardItem, SubMenu};
use ksni::{Icon, MenuItem, ToolTip};
use whispy_core::json::Json;

use crate::controller::Status;
use crate::i18n::{self, fill, tr, Language, Text};
use crate::log;
use crate::settings;
use crate::update::{Row, Updater};

/// The icon's side, in pixels: panels scale it, 22 is the usual tray size.
pub const ICON_SIZE: i32 = 22;

/// Rest: a grey ring. Listening: a red dot.
const REST_RGB: [u8; 3] = [0x9e, 0x9e, 0x9e];
const LISTENING_RGB: [u8; 3] = [0xe5, 0x39, 0x35];

pub struct WhispyTray {
    pub listening: bool,
    /// The controller's last status; `None` until its first (the models load).
    pub status: Option<Status>,
    /// The update row, as the updater last reported it; `None`: up to date.
    pub update: Option<Row>,
    /// The `language` setting, checked in « Language: … ».
    pub language: Language,
    /// Where the language choice is saved; `None` without HOME.
    settings_path: Option<PathBuf>,
    updater: Updater,
    quit: Sender<()>,
}

impl WhispyTray {
    pub fn new(
        quit: Sender<()>,
        updater: Updater,
        language: Language,
        settings_path: Option<PathBuf>,
    ) -> WhispyTray {
        WhispyTray {
            listening: false,
            status: None,
            update: updater.row(),
            language,
            settings_path,
            updater,
            quit,
        }
    }

    /// The status line (« Ready — hold the trigger key to dictate », a problem).
    pub fn status_line(&self) -> String {
        match &self.status {
            Some(status) => status.line(),
            None => tr(Text::HeadlineLoading).to_string(),
        }
    }

    /// Saves the choice, then puts it in force: the next menu the host asks
    /// for, every notification after it, and the next start follow it.
    fn select_language(&mut self, language: Language) {
        let saved = match &self.settings_path {
            Some(path) => settings::save_key(
                path,
                "language",
                Json::Text(language.as_config().to_string()),
            ),
            None => Err("the settings path is unknown (no HOME)".to_string()),
        };
        if let Err(error) = saved {
            log::line(&format!("could not save language: {error}"));
            return;
        }
        let lang = i18n::apply(language);
        log::line(&format!(
            "language: {} ({})",
            language.as_config(),
            lang.code()
        ));
        self.language = language;
        self.update = self.updater.row();
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
            description: self.status_line(),
            ..Default::default()
        }
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        let mut items = vec![
            StandardItem {
                label: self.status_line(),
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
            SubMenu {
                label: fill(Text::MenuLanguage, &[("language", self.language.label())]),
                submenu: vec![RadioGroup {
                    selected: Language::ALL
                        .iter()
                        .position(|language| *language == self.language)
                        .unwrap_or(0),
                    select: Box::new(|tray: &mut Self, at| {
                        if let Some(language) = Language::ALL.get(at) {
                            tray.select_language(*language);
                        }
                    }),
                    options: Language::ALL
                        .iter()
                        .map(|language| RadioItem {
                            label: language.label().to_string(),
                            ..Default::default()
                        })
                        .collect(),
                }
                .into()],
                ..Default::default()
            }
            .into(),
        );
        items.push(
            StandardItem {
                label: tr(Text::MenuQuit).into(),
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
pub fn spawn(
    quit: Sender<()>,
    updater: Updater,
    language: Language,
    settings_path: Option<PathBuf>,
) -> Result<Handle<WhispyTray>, String> {
    WhispyTray::new(quit, updater, language, settings_path)
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
                MenuItem::SubMenu(item) => Some(item.label.clone()),
                _ => None,
            })
            .collect()
    }

    fn ready() -> Option<Status> {
        Some(Status {
            state: crate::machine::State::Idle,
            note: None,
            models_loaded: true,
            trigger_mode: crate::settings::TriggerMode::Hold,
            permission_pane: None,
        })
    }

    fn tray(quit: Sender<()>, updater: Updater) -> WhispyTray {
        WhispyTray::new(quit, updater, Language::System, None)
    }

    #[test]
    fn up_to_date_the_menu_shows_the_status_and_quit_reaches_the_app() {
        let (quit, quitted) = std::sync::mpsc::channel();
        let mut tray = tray(quit, test_updater());
        assert_eq!(labels(&tray)[0], "Loading the models\u{2026}");
        tray.status = ready();
        assert_eq!(
            labels(&tray),
            [
                "Ready \u{2014} hold the trigger key to dictate",
                "Language: System",
                "Quit"
            ]
        );
        let menu = ksni::Tray::menu(&tray);
        if let MenuItem::Standard(quit_item) = &menu[3] {
            (quit_item.activate)(&mut tray);
        }
        assert!(quitted.try_recv().is_ok());
    }

    #[test]
    fn choosing_a_language_saves_it_and_redraws_the_menu_in_it() {
        let directory = std::env::temp_dir().join(format!(
            "whispy2-tray-language-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        let path = directory.join("config.json");
        let (quit, _quitted) = std::sync::mpsc::channel();
        let mut tray = WhispyTray::new(quit, test_updater(), Language::System, Some(path.clone()));
        tray.status = ready();
        let menu = ksni::Tray::menu(&tray);
        let MenuItem::SubMenu(language) = &menu[2] else {
            panic!("the language item is a submenu")
        };
        let MenuItem::RadioGroup(choices) = &language.submenu[0] else {
            panic!("the languages are a radio group")
        };
        let options: Vec<&str> = choices.options.iter().map(|o| o.label.as_str()).collect();
        assert_eq!(options, ["System", "Fran\u{e7}ais", "English"]);
        assert_eq!(choices.selected, 0);
        (choices.select)(&mut tray, 1);
        assert_eq!(tray.language, Language::French);
        assert_eq!(
            labels(&tray),
            [
                "Pr\u{ea}t \u{2014} maintenez la touche de dict\u{e9}e pour dicter",
                "Langue : Fran\u{e7}ais",
                "Quitter"
            ]
        );
        let (saved, _) = crate::settings::load(&path);
        assert_eq!(saved.language, Language::French);
        let _ = std::fs::remove_dir_all(&directory);
    }

    #[test]
    fn an_offered_update_shows_and_installs_on_its_own_click() {
        let (quit, _quitted) = std::sync::mpsc::channel();
        let updater = test_updater();
        let mut tray = tray(quit, updater.clone());
        updater.check();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while updater.row().is_none() {
            assert!(std::time::Instant::now() < deadline, "no offer");
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        tray.update = updater.row();
        tray.status = ready();
        assert_eq!(
            labels(&tray),
            [
                "Ready \u{2014} hold the trigger key to dictate",
                "Update available (2.5.0)",
                "Language: System",
                "Quit"
            ]
        );
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

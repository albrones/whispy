//! The menu as data: V1's `_build_menu`, without AppKit.
//!
//! [`build`] turns a [`MenuInput`] into an ordered list of [`MenuRow`]s that
//! `mac/menu_bar.rs` renders as `NSMenuItem`s. Keeping the order, titles and
//! check states here makes the "menu matches V1" scenario a plain unit test.
//! The module also holds V1's status-line precedence, trigger labels, System
//! Settings URLs and alert texts, all ported verbatim from
//! `src/whispy/ui/menu_bar.py`. Every text is drawn through [`crate::i18n`],
//! in the language in force when the menu is built.

use crate::i18n::{fill, tr, Language, Text};
use crate::theme::{check_title, section_title, status_title, toggle_title, Title};

/// V1's trigger presets: label and keycode (`None` is Fn, stored as unset;
/// its keycode is [`FN_KEYCODE`]).
pub const TRIGGER_PRESETS: [(Text, Option<i64>); 4] = [
    (Text::KeyFn, None),
    (Text::KeyRightCommand, Some(54)),
    (Text::KeyRightOption, Some(61)),
    (Text::KeyF13, Some(105)),
];

/// The Fn key's keycode, what the unset trigger means.
pub const FN_KEYCODE: i64 = 63;

/// Whispy's version, as the last release tag stamped it into Cargo.toml
/// (scripts/release.py, run by the release workflow on every feat or fix).
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// The menu's first row: « Whispy 2.1.0 · voice dictation ».
pub fn header_title() -> String {
    fill(Text::MenuHeader, &[("version", VERSION)])
}

/// What a menu item does when chosen.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MenuAction {
    ToggleCopy,
    ToggleMode,
    ToggleTypeWhileSpeaking,
    /// `None` selects Fn (the default, stored as unset).
    SelectTrigger(Option<i64>),
    /// « Language: System / Français / English ».
    SelectLanguage(Language),
    ToggleLogin,
    OpenPermissionSettings,
    /// « Update available (X.Y.Z) »: installs it.
    InstallUpdate,
    Restart,
    Quit,
}

/// What a row is, and what it carries beyond its title.
#[derive(Debug, Clone, PartialEq)]
pub enum RowKind {
    /// Disabled caption at the top.
    Header,
    /// Disabled status line.
    Status,
    /// The « Missing permission » item, hidden until a permission alert.
    PermissionWarning {
        visible: bool,
    },
    Separator,
    /// Disabled section header.
    Section,
    Toggle {
        action: MenuAction,
        checked: bool,
    },
    Submenu {
        items: Vec<MenuRow>,
    },
    Choice {
        action: MenuAction,
        checked: bool,
    },
    Action {
        action: MenuAction,
        key_equivalent: Option<&'static str>,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct MenuRow {
    pub kind: RowKind,
    pub title: Title,
    pub enabled: bool,
}

impl MenuRow {
    fn new(kind: RowKind, title: Title, enabled: bool) -> MenuRow {
        MenuRow {
            kind,
            title,
            enabled,
        }
    }
}

/// How « Start at login » appears.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LoginRow {
    /// No row at all.
    Hidden,
    /// Shown disabled: not running from the installed app.
    Unavailable,
    On,
    Off,
    /// Registered but waiting for the user's approval in System Settings. V1
    /// has no such state; shown as an unticked toggle that says so.
    NeedsApproval,
}

/// Everything the menu depends on, free of controller types.
#[derive(Debug, Clone, PartialEq)]
pub struct MenuInput {
    /// The status line text (see [`status_text`]).
    pub status_text: String,
    pub copy_to_clipboard: bool,
    pub toggle_mode: bool,
    /// V1's `type_while_speaking`. Like V1, the row shows the setting alone:
    /// it only acts in toggle mode, and V1 does not flag it in hold mode.
    pub type_while_speaking: bool,
    /// The configured trigger's keycode ([`FN_KEYCODE`] for Fn).
    pub trigger_keycode: i64,
    /// The label shown in « Trigger: <label> » (see [`trigger_label`]).
    pub trigger_label: String,
    /// The `language` setting, checked in « Language: … ».
    pub language: Language,
    pub login: LoginRow,
    pub permission_warning: bool,
    /// The update row (see [`crate::update`]): a grey status line at rest.
    pub update: crate::update::Row,
    pub dark: bool,
}

/// The facts the status line is chosen from.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct StatusFacts {
    pub trigger_down: bool,
    pub recording: bool,
    pub transcribing: bool,
    pub model_loading: bool,
    pub model_loaded: bool,
    /// V2 is leaving the trigger to a running Whispy V1.
    pub yielded: bool,
}

/// V1's status precedence (`_update_status_on_main`): trigger down and not
/// recording, loading, model missing, recording, transcribing, ready. V1 has
/// no yielding; here it comes first, because while yielded V2 listens to
/// nothing, so every other line would be misleading.
pub fn status_text(f: &StatusFacts) -> &'static str {
    tr(if f.yielded {
        Text::StatusYielded
    } else if f.trigger_down && !f.recording {
        Text::StatusListening
    } else if f.model_loading {
        Text::StatusLoadingModel
    } else if !f.model_loaded {
        Text::StatusModelNotLoaded
    } else if f.recording {
        Text::StatusRecording
    } else if f.transcribing {
        Text::StatusTranscribing
    } else {
        Text::StatusReady
    })
}

/// Whether the preset `value` is the configured trigger (Fn is `None`).
fn preset_active(value: Option<i64>, keycode: i64) -> bool {
    value.unwrap_or(FN_KEYCODE) == keycode
}

/// V1's `_trigger_label`: the preset's label when one matches, else the
/// keycode's name (a hand-edited config).
pub fn trigger_label(keycode: i64) -> String {
    for (label, value) in TRIGGER_PRESETS {
        if preset_active(value, keycode) {
            return tr(label).to_string();
        }
    }
    keycode_to_name(keycode)
}

/// V1's `keycode_to_name`: a readable name, or `keyNN`.
pub fn keycode_to_name(keycode: i64) -> String {
    match KEYCODE_NAMES.iter().find(|(k, _)| *k == keycode) {
        Some((_, name)) => (*name).to_string(),
        None => format!("key{keycode}"),
    }
}

/// The menu, top to bottom, as V1's `_build_menu` lays it out.
pub fn build(input: &MenuInput) -> Vec<MenuRow> {
    let _ = input.dark; // The colour is applied by the renderer from `theme::accent`.
    let mut rows = vec![
        MenuRow::new(RowKind::Header, Title::plain(header_title()), false),
        MenuRow::new(RowKind::Status, status_title(&input.status_text), false),
        MenuRow::new(
            RowKind::PermissionWarning {
                visible: input.permission_warning,
            },
            Title::plain(tr(Text::MenuPermissionWarning)),
            true,
        ),
        separator(),
        MenuRow::new(
            RowKind::Section,
            section_title(tr(Text::MenuSettings)),
            false,
        ),
        toggle(
            tr(Text::MenuCopyToClipboard),
            input.copy_to_clipboard,
            MenuAction::ToggleCopy,
        ),
        toggle(
            tr(Text::MenuToggleMode),
            input.toggle_mode,
            MenuAction::ToggleMode,
        ),
        toggle(
            tr(Text::MenuTypeWhileSpeaking),
            input.type_while_speaking,
            MenuAction::ToggleTypeWhileSpeaking,
        ),
    ];

    let items = TRIGGER_PRESETS
        .iter()
        .map(|&(label, value)| {
            let checked = preset_active(value, input.trigger_keycode);
            MenuRow::new(
                RowKind::Choice {
                    action: MenuAction::SelectTrigger(value),
                    checked,
                },
                check_title(tr(label), checked),
                true,
            )
        })
        .collect();
    rows.push(MenuRow::new(
        RowKind::Submenu { items },
        Title::plain(fill(Text::MenuTrigger, &[("key", &input.trigger_label)])),
        true,
    ));
    rows.push(language_row(input.language));

    match input.login {
        LoginRow::Hidden => {}
        LoginRow::Unavailable => rows.push(MenuRow::new(
            RowKind::Toggle {
                action: MenuAction::ToggleLogin,
                checked: false,
            },
            Title::plain(tr(Text::MenuStartAtLoginUnavailable)),
            false,
        )),
        LoginRow::On => rows.push(toggle(
            tr(Text::MenuStartAtLogin),
            true,
            MenuAction::ToggleLogin,
        )),
        LoginRow::Off => rows.push(toggle(
            tr(Text::MenuStartAtLogin),
            false,
            MenuAction::ToggleLogin,
        )),
        LoginRow::NeedsApproval => rows.push(toggle(
            tr(Text::MenuStartAtLoginNeedsApproval),
            false,
            MenuAction::ToggleLogin,
        )),
    }

    rows.push(separator());
    rows.push(update_row(&input.update));
    rows.push(MenuRow::new(
        RowKind::Action {
            action: MenuAction::Restart,
            key_equivalent: None,
        },
        Title::plain(tr(Text::MenuRestart)),
        true,
    ));
    rows.push(MenuRow::new(
        RowKind::Action {
            action: MenuAction::Quit,
            key_equivalent: Some("q"),
        },
        Title::plain(tr(Text::MenuQuit)),
        true,
    ));
    rows
}

/// « Language: System », its submenu checking the setting in force.
pub fn language_row(setting: Language) -> MenuRow {
    let items = Language::ALL
        .iter()
        .map(|&language| {
            let checked = language == setting;
            MenuRow::new(
                RowKind::Choice {
                    action: MenuAction::SelectLanguage(language),
                    checked,
                },
                check_title(language.label(), checked),
                true,
            )
        })
        .collect();
    MenuRow::new(
        RowKind::Submenu { items },
        Title::plain(fill(Text::MenuLanguage, &[("language", setting.label())])),
        true,
    )
}

/// The update row: disabled (grey) at rest and while an install runs.
pub fn update_row(row: &crate::update::Row) -> MenuRow {
    MenuRow::new(
        RowKind::Action {
            action: MenuAction::InstallUpdate,
            key_equivalent: None,
        },
        Title::plain(row.title.clone()),
        row.enabled,
    )
}

fn separator() -> MenuRow {
    MenuRow::new(RowKind::Separator, Title::plain(""), false)
}

fn toggle(text: &str, checked: bool, action: MenuAction) -> MenuRow {
    MenuRow::new(
        RowKind::Toggle { action, checked },
        toggle_title(text, checked),
        true,
    )
}

/// A System Settings privacy pane.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pane {
    Microphone,
    InputMonitoring,
    Accessibility,
    Automation,
}

impl Pane {
    /// V1's `kind` strings; anything unknown falls back to Accessibility, as
    /// V1's `_SETTINGS_URLS.get(kind, accessibility)` does.
    pub fn from_kind(kind: &str) -> Pane {
        match kind {
            "microphone" => Pane::Microphone,
            "input_monitoring" => Pane::InputMonitoring,
            "automation" => Pane::Automation,
            _ => Pane::Accessibility,
        }
    }
}

/// The deep link that opens `pane`.
pub fn settings_url(pane: Pane) -> &'static str {
    match pane {
        Pane::Microphone => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        }
        Pane::InputMonitoring => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        }
        Pane::Accessibility => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        }
        Pane::Automation => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
        }
    }
}

/// A notification titled « Whispy ». `pane` is set for permission alerts: they
/// also reveal the warning item and point its click at that pane.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Alert {
    pub subtitle: String,
    pub message: String,
    pub pane: Option<Pane>,
}

impl Alert {
    fn new(subtitle: Text, message: String, pane: Option<Pane>) -> Alert {
        Alert {
            subtitle: tr(subtitle).to_string(),
            message,
            pane,
        }
    }

    /// A startup probe reported an explicit denial; `kind` is V1's string.
    pub fn missing_permission(kind: &str, message: &str) -> Alert {
        Alert::new(
            Text::AlertMissingPermission,
            message.to_string(),
            Some(Pane::from_kind(kind)),
        )
    }

    pub fn cannot_type(message: &str) -> Alert {
        Alert::new(
            Text::AlertCannotType,
            message.to_string(),
            Some(Pane::Accessibility),
        )
    }

    /// First launch: the models are being fetched, dictation waits for them.
    pub fn downloading_models(megabytes: u64) -> Alert {
        Alert::new(
            Text::AlertDownloadingModels,
            fill(
                Text::AlertDownloadingModelsMessage,
                &[("megabytes", &megabytes.to_string())],
            ),
            None,
        )
    }

    pub fn model_failed(message: &str) -> Alert {
        Alert::new(
            Text::AlertModelFailed,
            fill(Text::AlertModelFailedMessage, &[("message", message)]),
            None,
        )
    }

    pub fn no_microphone(message: &str) -> Alert {
        Alert::new(
            Text::AlertNoMicrophone,
            fill(Text::AlertNoMicrophoneMessage, &[("message", message)]),
            None,
        )
    }

    pub fn microphone_heard_nothing(message: &str) -> Alert {
        Alert::new(Text::AlertHeardNothing, message.to_string(), None)
    }

    pub fn dictation_stopped(message: &str) -> Alert {
        Alert::new(Text::AlertDictationStopped, message.to_string(), None)
    }

    /// Linux: the trigger key cannot be listened to; `message` says why and what still works.
    pub fn trigger_key_unavailable(message: &str) -> Alert {
        Alert::new(Text::AlertTriggerKeyUnavailable, message.to_string(), None)
    }

    /// Linux: the tray icon could not start; Whispy runs on without it.
    pub fn tray_unavailable(reason: &str) -> Alert {
        Alert::new(
            Text::AlertTrayUnavailable,
            fill(Text::AlertTrayUnavailableMessage, &[("reason", reason)]),
            None,
        )
    }

    pub fn model_still_loading() -> Alert {
        Alert::new(
            Text::AlertModelStillLoading,
            tr(Text::AlertModelStillLoadingMessage).to_string(),
            None,
        )
    }
}

/// V1's `_KEYCODE_TO_NAME` table (`hardware/event_decode.py`).
const KEYCODE_NAMES: [(i64, &str); 95] = [
    (0, "a"),
    (1, "s"),
    (2, "d"),
    (3, "f"),
    (4, "h"),
    (5, "g"),
    (6, "z"),
    (7, "x"),
    (8, "c"),
    (9, "v"),
    (11, "b"),
    (12, "q"),
    (13, "w"),
    (14, "e"),
    (15, "r"),
    (16, "y"),
    (17, "t"),
    (18, "1"),
    (19, "2"),
    (20, "3"),
    (21, "4"),
    (22, "6"),
    (23, "5"),
    (24, "="),
    (25, "9"),
    (26, "7"),
    (27, "-"),
    (28, "8"),
    (29, "0"),
    (30, "]"),
    (31, "o"),
    (32, "u"),
    (33, "["),
    (34, "i"),
    (35, "p"),
    (36, "enter"),
    (37, "l"),
    (38, "j"),
    (39, "'"),
    (40, "k"),
    (41, ";"),
    (42, "\\"),
    (43, ","),
    (44, "/"),
    (45, "n"),
    (46, "m"),
    (47, "."),
    (48, "tab"),
    (49, "space"),
    (50, "`"),
    (51, "backspace"),
    (53, "escape"),
    (54, "right_command"),
    (55, "command"),
    (56, "shift"),
    (57, "caps_lock"),
    (58, "option"),
    (59, "control"),
    (60, "right_shift"),
    (61, "right_option"),
    (62, "right_control"),
    (63, "fn"),
    (64, "f17"),
    (72, "volume_up"),
    (73, "volume_down"),
    (74, "mute"),
    (79, "f18"),
    (80, "f19"),
    (90, "f20"),
    (96, "f5"),
    (97, "f6"),
    (98, "f7"),
    (99, "f3"),
    (100, "f8"),
    (101, "f9"),
    (103, "f11"),
    (105, "f13"),
    (106, "f16"),
    (107, "f14"),
    (109, "f10"),
    (111, "f12"),
    (113, "f15"),
    (114, "help"),
    (115, "home"),
    (116, "page_up"),
    (117, "delete"),
    (118, "f4"),
    (119, "end"),
    (120, "f2"),
    (121, "page_down"),
    (122, "f1"),
    (123, "left"),
    (124, "right"),
    (125, "down"),
    (126, "up"),
];

#[cfg(test)]
mod tests {
    use super::*;

    fn idle_input() -> MenuInput {
        MenuInput {
            status_text: "Ready".into(),
            copy_to_clipboard: true,
            toggle_mode: false,
            type_while_speaking: true,
            trigger_keycode: FN_KEYCODE,
            trigger_label: trigger_label(FN_KEYCODE),
            language: Language::System,
            login: LoginRow::Hidden,
            permission_warning: false,
            update: crate::update::Row {
                title: "Whispy 2.6.0 \u{b7} up to date".into(),
                enabled: false,
                transient: false,
            },
            dark: true,
        }
    }

    #[test]
    fn the_first_launch_download_says_its_size_and_when_dictation_works() {
        let alert = Alert::downloading_models(1158);
        assert_eq!(alert.subtitle, "Downloading the speech models");
        assert!(alert.message.contains("1158 MB"));
        assert!(alert.message.contains("Ready"));
        assert_eq!(alert.pane, None);
    }

    #[test]
    fn the_header_names_the_version_of_the_last_release() {
        // scripts/release.py stamps the same version into the crate and the
        // website's menu demo on each release; the menu shows the crate's.
        let website = include_str!("../../../website/index.html");
        let stamped = website
            .split("<div class=\"dd-header\">Whispy ")
            .nth(1)
            .and_then(|rest| rest.split(' ').next())
            .expect("website/index.html states the version");
        assert_eq!(VERSION, stamped);
        assert_eq!(
            build(&idle_input())[0].title.text,
            format!("Whispy {stamped} \u{b7} voice dictation")
        );
    }

    #[test]
    fn menu_matches_v1() {
        let rows = build(&idle_input());
        let titles: Vec<&str> = rows.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(
            titles,
            [
                header_title().as_str(),
                "●  Ready",
                "\u{26a0} Missing permission \u{2014} fix in System Settings\u{2026}",
                "",
                "SETTINGS",
                "Copy to clipboard   ✓",
                "Toggle mode",
                "Type while speaking   ✓",
                "Trigger: Fn",
                "Language: System",
                "",
                "Whispy 2.6.0 \u{b7} up to date",
                "Restart",
                "Quit",
            ]
        );
        assert_eq!(rows[2].kind, RowKind::PermissionWarning { visible: false });
        assert!(!rows[0].enabled && !rows[1].enabled && !rows[4].enabled);
        assert!(!rows[11].enabled, "the version line is grey");
        assert_eq!(
            rows[7].kind,
            RowKind::Toggle {
                action: MenuAction::ToggleTypeWhileSpeaking,
                checked: true
            }
        );
        assert_eq!(
            rows[13].kind,
            RowKind::Action {
                action: MenuAction::Quit,
                key_equivalent: Some("q")
            }
        );
    }

    #[test]
    fn the_language_submenu_offers_system_french_english_and_checks_the_setting() {
        let mut input = idle_input();
        input.language = Language::English;
        let row = &build(&input)[9];
        assert_eq!(row.title.text, "Language: English");
        let RowKind::Submenu { items } = &row.kind else {
            panic!("not a submenu")
        };
        let titles: Vec<&str> = items.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(titles, ["      System", "      Français", "✓  English"]);
        assert_eq!(
            items[1].kind,
            RowKind::Choice {
                action: MenuAction::SelectLanguage(Language::French),
                checked: false
            }
        );
    }

    #[test]
    fn in_french_every_row_of_the_menu_is_french() {
        use crate::i18n::{set, Lang};
        set(Lang::Fr);
        let mut input = idle_input();
        input.login = LoginRow::On;
        input.update = crate::update::Row {
            title: crate::update::texts::available(crate::update::Version(2, 6, 0)),
            enabled: true,
            transient: false,
        };
        input.status_text = status_text(&StatusFacts {
            model_loaded: true,
            ..Default::default()
        })
        .to_string();
        input.trigger_label = trigger_label(54);
        let rows = build(&input);
        let titles: Vec<&str> = rows.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(
            titles,
            [
                format!("Whispy {VERSION} \u{b7} dictée vocale").as_str(),
                "●  Prêt",
                "\u{26a0} Autorisation manquante \u{2014} à corriger dans Réglages Système\u{2026}",
                "",
                "RÉGLAGES",
                "Copier dans le presse-papiers   ✓",
                "Mode bascule",
                "Écrire pendant la dictée   ✓",
                "Touche : Commande droite",
                "Langue : Système",
                "Ouvrir à la connexion   ✓",
                "",
                "Mise à jour disponible (2.6.0)",
                "Redémarrer",
                "Quitter",
            ]
        );
        let RowKind::Submenu { items } = &rows[9].kind else {
            panic!("not a submenu")
        };
        let languages: Vec<&str> = items.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(languages, ["✓  Système", "      Français", "      English"]);
        assert_eq!(
            Alert::model_still_loading().subtitle,
            "Modèle en cours de chargement"
        );
        // Choosing English redraws the same menu in English, without a restart.
        set(Lang::En);
        assert_eq!(build(&input)[13].title.text, "Restart");
    }

    #[test]
    fn trigger_submenu_checks_the_active_preset() {
        let RowKind::Submenu { items } = &build(&idle_input())[8].kind else {
            panic!("not a submenu")
        };
        let titles: Vec<&str> = items.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(
            titles,
            [
                "✓  Fn",
                "      Right Command",
                "      Right Option",
                "      F13"
            ]
        );
        assert_eq!(
            items[1].kind,
            RowKind::Choice {
                action: MenuAction::SelectTrigger(Some(54)),
                checked: false
            }
        );
        assert_eq!(
            items[0].kind,
            RowKind::Choice {
                action: MenuAction::SelectTrigger(None),
                checked: true
            }
        );
    }

    #[test]
    fn login_row_follows_its_state() {
        let mut i = idle_input();
        let tail = |i: &MenuInput| {
            build(i)
                .into_iter()
                .map(|r| r.title.text)
                .collect::<Vec<_>>()
        };
        assert!(!tail(&i).iter().any(|t| t.starts_with("Start at login")));
        i.login = LoginRow::Unavailable;
        let rows = build(&i);
        assert_eq!(
            rows[10].title.text,
            "Start at login (needs the installed app)"
        );
        assert!(!rows[10].enabled);
        i.login = LoginRow::On;
        assert_eq!(build(&i)[10].title.text, "Start at login   ✓");
        i.login = LoginRow::Off;
        assert_eq!(build(&i)[10].title.text, "Start at login");
    }

    #[test]
    fn type_while_speaking_row_follows_the_setting() {
        let mut i = idle_input();
        i.type_while_speaking = false;
        let row = &build(&i)[7];
        assert_eq!(row.title.text, "Type while speaking");
        assert_eq!(
            row.kind,
            RowKind::Toggle {
                action: MenuAction::ToggleTypeWhileSpeaking,
                checked: false
            }
        );
    }

    #[test]
    fn the_update_row_is_a_grey_status_line_until_an_offer_installs_on_click() {
        use crate::update::Row;
        let mut input = idle_input();
        let rows = build(&input);
        let titles: Vec<&str> = rows.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(
            &titles[titles.len() - 3..],
            ["Whispy 2.6.0 \u{b7} up to date", "Restart", "Quit"]
        );
        assert!(
            !rows[rows.len() - 3].enabled,
            "up to date: grey, not clickable"
        );
        input.update = Row {
            title: "Update available (2.5.0)".into(),
            enabled: true,
            transient: false,
        };
        let rows = build(&input);
        let titles: Vec<&str> = rows.iter().map(|r| r.title.text.as_str()).collect();
        assert_eq!(
            &titles[titles.len() - 3..],
            ["Update available (2.5.0)", "Restart", "Quit"]
        );
        let offer = update_row(&input.update);
        assert_eq!(offer.title.text, "Update available (2.5.0)");
        assert!(offer.enabled);
        assert_eq!(
            offer.kind,
            RowKind::Action {
                action: MenuAction::InstallUpdate,
                key_equivalent: None
            }
        );
        let busy = update_row(&Row {
            title: "Updating to 2.5.0\u{2026}".into(),
            enabled: false,
            transient: true,
        });
        assert!(!busy.enabled);
    }

    #[test]
    fn permission_warning_is_visible_when_flagged() {
        let mut i = idle_input();
        i.permission_warning = true;
        assert_eq!(
            build(&i)[2].kind,
            RowKind::PermissionWarning { visible: true }
        );
    }

    #[test]
    fn appearance_switch_changes_the_accent() {
        use crate::theme::accent;
        let mut i = idle_input();
        let dark = build(&i);
        i.dark = false;
        let light = build(&i);
        // The model is the same; the renderer picks the colour from `dark`.
        assert_eq!(dark, light);
        assert_ne!(accent(true), accent(false));
        assert_eq!(accent(false), (0x1C, 0x9A, 0x7F));
    }

    #[test]
    fn trigger_label_for_preset_and_hand_set_keycode() {
        assert_eq!(trigger_label(63), "Fn");
        assert_eq!(trigger_label(54), "Right Command");
        assert_eq!(trigger_label(105), "F13");
        assert_eq!(trigger_label(107), "f14");
        assert_eq!(trigger_label(250), "key250");
    }

    #[test]
    fn status_precedence_matches_v1() {
        let base = StatusFacts {
            model_loaded: true,
            ..Default::default()
        };
        assert_eq!(status_text(&base), "Ready");
        assert_eq!(
            status_text(&StatusFacts {
                trigger_down: true,
                ..base
            }),
            "Listening\u{2026}"
        );
        // Trigger down while recording is "Recording", not "Listening".
        assert_eq!(
            status_text(&StatusFacts {
                trigger_down: true,
                recording: true,
                ..base
            }),
            "Recording"
        );
        assert_eq!(
            status_text(&StatusFacts {
                transcribing: true,
                ..base
            }),
            "Transcribing\u{2026}"
        );
        assert_eq!(
            status_text(&StatusFacts {
                model_loading: true,
                ..base
            }),
            "Loading model\u{2026}"
        );
        assert_eq!(
            status_text(&StatusFacts::default()),
            "\u{26a0} Model not loaded"
        );
        // Loading beats a missing model; listening beats loading.
        assert_eq!(
            status_text(&StatusFacts {
                model_loading: true,
                trigger_down: true,
                ..Default::default()
            }),
            "Listening\u{2026}"
        );
        assert_eq!(
            status_text(&StatusFacts {
                yielded: true,
                recording: true,
                ..base
            }),
            "Whispy V1 is running \u{2014} the trigger key is left to it"
        );
    }

    #[test]
    fn settings_url_per_pane() {
        assert!(settings_url(Pane::Microphone).ends_with("?Privacy_Microphone"));
        assert!(settings_url(Pane::InputMonitoring).ends_with("?Privacy_ListenEvent"));
        assert!(settings_url(Pane::Accessibility).ends_with("?Privacy_Accessibility"));
        assert!(settings_url(Pane::Automation).ends_with("?Privacy_Automation"));
        assert!(settings_url(Pane::Automation)
            .starts_with("x-apple.systempreferences:com.apple.preference.security?"));
        assert_eq!(Pane::from_kind("bogus"), Pane::Accessibility);
    }

    #[test]
    fn alerts_carry_v1_texts() {
        let a = Alert::missing_permission("microphone", "Mic denied");
        assert_eq!(
            (a.subtitle.as_str(), a.message.as_str(), a.pane),
            ("Missing permission", "Mic denied", Some(Pane::Microphone))
        );
        assert_eq!(Alert::cannot_type("x").pane, Some(Pane::Accessibility));
        assert_eq!(
            Alert::model_failed("offline").message,
            "offline \u{2014} check your internet connection, then use Restart from the Whispy menu."
        );
        assert_eq!(
            Alert::no_microphone("none").message,
            "none \u{2014} check your input device, then try again."
        );
        assert_eq!(
            Alert::microphone_heard_nothing("m").subtitle,
            "Microphone heard nothing"
        );
        assert_eq!(Alert::dictation_stopped("m").subtitle, "Dictation stopped");
        let l = Alert::model_still_loading();
        assert_eq!(l.subtitle, "Model still loading");
        assert_eq!(l.pane, None);
    }
}

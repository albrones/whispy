//! The interface's language: French when the system is in French, English
//! otherwise, unless the `language` setting forces one (#64).
//!
//! Every text the user reads (menus, status lines, notifications, the update
//! row) lives in one translation file per language, `i18n/en.json` and
//! `i18n/fr.json`, keyed by the [`Text`] it renders. The tests fail when a key
//! is missing from either file, when a file holds a key no [`Text`] names, or
//! when the two files disagree on a text's `{placeholders}`.
//!
//! The language in force is process-wide ([`set`], [`current`]): a choice in
//! the menu applies at once, and every text drawn afterwards follows it.
//! Logs stay in English ([`tr_in`] with [`Lang::En`]).

use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::OnceLock;

use whispy_core::json::{parse_json, Json};

/// A language the interface is written in.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    En,
    Fr,
}

impl Lang {
    pub const ALL: [Lang; 2] = [Lang::En, Lang::Fr];

    /// The code the control socket and the Omarchy panel use.
    pub fn code(self) -> &'static str {
        match self {
            Lang::En => "en",
            Lang::Fr => "fr",
        }
    }

    fn source(self) -> &'static str {
        match self {
            Lang::En => include_str!("../i18n/en.json"),
            Lang::Fr => include_str!("../i18n/fr.json"),
        }
    }
}

/// The `language` setting: follow the system, or force a language.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    System,
    French,
    English,
}

impl Language {
    /// In the order of the menu: « Language: System / Français / English ».
    pub const ALL: [Language; 3] = [Language::System, Language::French, Language::English];

    /// The value stored in `language`.
    pub fn as_config(self) -> &'static str {
        match self {
            Language::System => "system",
            Language::French => "fr",
            Language::English => "en",
        }
    }

    pub fn from_config(value: &str) -> Option<Language> {
        Language::ALL
            .into_iter()
            .find(|language| language.as_config() == value)
    }

    /// Its name in the menu.
    pub fn label(self) -> &'static str {
        tr(match self {
            Language::System => Text::LanguageSystem,
            Language::French => Text::LanguageFr,
            Language::English => Text::LanguageEn,
        })
    }
}

/// French for a `fr` locale tag (`fr`, `fr-FR`, `fr_CA.UTF-8`), English for any other.
pub fn lang_of_tag(tag: &str) -> Lang {
    let primary = tag
        .split(['-', '_', '.', '@'])
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    if primary == "fr" {
        Lang::Fr
    } else {
        Lang::En
    }
}

/// The Linux locale for messages, as `setlocale` reads it: `LC_ALL`, then
/// `LC_MESSAGES`, then `LANG`; the first one set and not empty decides.
pub fn lang_of_env(var: impl Fn(&str) -> Option<String>) -> Lang {
    ["LC_ALL", "LC_MESSAGES", "LANG"]
        .into_iter()
        .filter_map(var)
        .find(|value| !value.is_empty())
        .map_or(Lang::En, |value| lang_of_tag(&value))
}

/// The system's language: the first of the user's preferred languages on
/// macOS, the locale environment under Linux.
pub fn system_lang() -> Lang {
    #[cfg(target_os = "macos")]
    {
        use objc2_foundation::NSLocale;
        let preferred = NSLocale::preferredLanguages();
        preferred
            .iter()
            .next()
            .map_or(Lang::En, |tag| lang_of_tag(&tag.to_string()))
    }
    #[cfg(not(target_os = "macos"))]
    {
        lang_of_env(|name| std::env::var(name).ok())
    }
}

/// The language a setting gives on this system.
pub fn resolve(language: Language) -> Lang {
    match language {
        Language::System => system_lang(),
        Language::French => Lang::Fr,
        Language::English => Lang::En,
    }
}

static CURRENT: AtomicU8 = AtomicU8::new(0);

#[cfg(test)]
thread_local! {
    /// Under test the language is the calling thread's, so tests that switch
    /// it run in parallel with tests that expect English.
    static TEST_LANG: std::cell::Cell<Option<Lang>> = const { std::cell::Cell::new(None) };
}

/// The language every text is drawn in from now on.
pub fn set(lang: Lang) {
    #[cfg(test)]
    TEST_LANG.with(|cell| cell.set(Some(lang)));
    #[cfg(not(test))]
    CURRENT.store(lang as u8, Ordering::SeqCst);
}

pub fn current() -> Lang {
    #[cfg(test)]
    if let Some(lang) = TEST_LANG.with(std::cell::Cell::get) {
        return lang;
    }
    match CURRENT.load(Ordering::SeqCst) {
        1 => Lang::Fr,
        _ => Lang::En,
    }
}

/// Puts the setting in force and says which language it gave.
pub fn apply(language: Language) -> Lang {
    let lang = resolve(language);
    set(lang);
    lang
}

macro_rules! texts {
    ($($name:ident => $key:literal,)*) => {
        /// A text of the interface; its key names it in the translation files.
        #[derive(Debug, Clone, Copy, PartialEq, Eq)]
        pub enum Text {
            $($name,)*
        }

        impl Text {
            pub const ALL: &'static [Text] = &[$(Text::$name,)*];

            pub fn key(self) -> &'static str {
                match self {
                    $(Text::$name => $key,)*
                }
            }
        }
    };
}

texts! {
    MenuHeader => "menu.header",
    MenuPermissionWarning => "menu.permission_warning",
    MenuSettings => "menu.settings",
    MenuCopyToClipboard => "menu.copy_to_clipboard",
    MenuToggleMode => "menu.toggle_mode",
    MenuTypeWhileSpeaking => "menu.type_while_speaking",
    MenuTrigger => "menu.trigger",
    MenuLanguage => "menu.language",
    MenuStartAtLogin => "menu.start_at_login",
    MenuStartAtLoginUnavailable => "menu.start_at_login_unavailable",
    MenuStartAtLoginNeedsApproval => "menu.start_at_login_needs_approval",
    MenuRestart => "menu.restart",
    MenuQuit => "menu.quit",
    MenuSaveFailed => "menu.save_failed",
    LanguageSystem => "language.system",
    LanguageFr => "language.fr",
    LanguageEn => "language.en",
    KeyFn => "key.fn",
    KeyRightCommand => "key.right_command",
    KeyRightOption => "key.right_option",
    KeyF13 => "key.f13",
    KeyRightCtrl => "key.right_ctrl",
    StatusYielded => "status.yielded",
    StatusListening => "status.listening",
    StatusLoadingModel => "status.loading_model",
    StatusModelNotLoaded => "status.model_not_loaded",
    StatusRecording => "status.recording",
    StatusTranscribing => "status.transcribing",
    StatusReady => "status.ready",
    HeadlineReadyHold => "headline.ready_hold",
    HeadlineReadyToggle => "headline.ready_toggle",
    HeadlineRecordingHold => "headline.recording_hold",
    HeadlineRecordingToggle => "headline.recording_toggle",
    HeadlineTranscribing => "headline.transcribing",
    HeadlineInserting => "headline.inserting",
    HeadlineLoading => "headline.loading",
    NoteTranscriptionFailed => "note.transcription_failed",
    NoteMicrophoneFailed => "note.microphone_failed",
    NoteModelsFailed => "note.models_failed",
    NoteHeardNothing => "note.heard_nothing",
    NoteHeardNothingOn => "note.heard_nothing_on",
    AlertMissingPermission => "alert.missing_permission",
    AlertCannotType => "alert.cannot_type",
    AlertDownloadingModels => "alert.downloading_models",
    AlertDownloadingModelsMessage => "alert.downloading_models_message",
    AlertModelFailed => "alert.model_failed",
    AlertModelFailedMessage => "alert.model_failed_message",
    AlertNoMicrophone => "alert.no_microphone",
    AlertNoMicrophoneMessage => "alert.no_microphone_message",
    AlertHeardNothing => "alert.heard_nothing",
    AlertDictationStopped => "alert.dictation_stopped",
    AlertDictationStoppedMessage => "alert.dictation_stopped_message",
    AlertTriggerKeyUnavailable => "alert.trigger_key_unavailable",
    AlertTriggerKeyUnavailableMessage => "alert.trigger_key_unavailable_message",
    AlertTrayUnavailable => "alert.tray_unavailable",
    AlertTrayUnavailableMessage => "alert.tray_unavailable_message",
    AlertModelStillLoading => "alert.model_still_loading",
    AlertModelStillLoadingMessage => "alert.model_still_loading_message",
    AlertInputMonitoringNotGranted => "alert.input_monitoring_not_granted",
    AlertAccessibilityRefusedPaste => "alert.accessibility_refused_paste",
    AlertAccessibilityRefusedTyping => "alert.accessibility_refused_typing",
    LoginApproval => "login.approval",
    LoginFailed => "login.failed",
    UpdateAvailable => "update.available",
    UpdateUpdatingTo => "update.updating_to",
    UpdateFailed => "update.failed",
    UpdateNotRestarted => "update.not_restarted",
    UpdateNeedsTerminal => "update.needs_terminal",
}

/// The translation files, parsed once: one table per [`Lang`], indexed like
/// [`Text::ALL`]. A text missing from a file is `None` there (the tests
/// forbid it; at run time French falls back to English).
fn tables() -> &'static [Vec<Option<String>>; 2] {
    static TABLES: OnceLock<[Vec<Option<String>>; 2]> = OnceLock::new();
    TABLES.get_or_init(|| Lang::ALL.map(|lang| table(lang.source())))
}

fn table(source: &str) -> Vec<Option<String>> {
    let parsed = parse_json(source).unwrap_or(Json::Null);
    Text::ALL
        .iter()
        .map(|text| {
            parsed
                .get(text.key())
                .and_then(Json::text)
                .map(str::to_string)
        })
        .collect()
}

fn index(text: Text) -> usize {
    Text::ALL
        .iter()
        .position(|t| *t == text)
        .expect("every Text is in Text::ALL")
}

/// `text` in `lang`.
pub fn tr_in(lang: Lang, text: Text) -> &'static str {
    let at = index(text);
    let [en, fr] = tables();
    let found = match lang {
        Lang::En => en[at].as_deref(),
        Lang::Fr => fr[at].as_deref().or(en[at].as_deref()),
    };
    found.unwrap_or(text.key())
}

/// `text` in the language in force.
pub fn tr(text: Text) -> &'static str {
    tr_in(current(), text)
}

/// `text` in `lang`, each `{name}` replaced by its value.
pub fn fill_in(lang: Lang, text: Text, values: &[(&str, &str)]) -> String {
    let mut out = tr_in(lang, text).to_string();
    for (name, value) in values {
        out = out.replace(&format!("{{{name}}}"), value);
    }
    out
}

/// `text` in the language in force, each `{name}` replaced by its value.
pub fn fill(text: Text, values: &[(&str, &str)]) -> String {
    fill_in(current(), text, values)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    fn keys(source: &str) -> Vec<String> {
        match parse_json(source).expect("the translation file is valid JSON") {
            Json::Object(fields) => fields.into_iter().map(|(key, _)| key).collect(),
            _ => panic!("the translation file is not a JSON object"),
        }
    }

    fn placeholders(text: &str) -> BTreeSet<String> {
        text.split('{')
            .skip(1)
            .filter_map(|rest| rest.split_once('}').map(|(name, _)| name.to_string()))
            .collect()
    }

    #[test]
    fn every_text_is_translated_in_both_languages() {
        for lang in Lang::ALL {
            let source = parse_json(lang.source()).unwrap();
            let missing: Vec<&str> = Text::ALL
                .iter()
                .map(|text| text.key())
                .filter(|key| {
                    source
                        .get(key)
                        .and_then(Json::text)
                        .is_none_or(str::is_empty)
                })
                .collect();
            assert!(
                missing.is_empty(),
                "i18n/{}.json lacks {missing:?}",
                lang.code()
            );
        }
    }

    #[test]
    fn the_files_hold_no_text_the_app_does_not_draw() {
        let known: BTreeSet<&str> = Text::ALL.iter().map(|text| text.key()).collect();
        assert_eq!(known.len(), Text::ALL.len(), "two texts share a key");
        for lang in Lang::ALL {
            let file = keys(lang.source());
            let unique: BTreeSet<&str> = file.iter().map(String::as_str).collect();
            assert_eq!(
                unique.len(),
                file.len(),
                "i18n/{}.json repeats a key",
                lang.code()
            );
            let unknown: Vec<&&str> = unique.difference(&known).collect();
            assert!(
                unknown.is_empty(),
                "i18n/{}.json: unknown {unknown:?}",
                lang.code()
            );
        }
    }

    #[test]
    fn both_languages_fill_the_same_placeholders() {
        for text in Text::ALL {
            assert_eq!(
                placeholders(tr_in(Lang::En, *text)),
                placeholders(tr_in(Lang::Fr, *text)),
                "{}",
                text.key()
            );
        }
    }

    #[test]
    fn french_tags_give_french_and_every_other_english() {
        for tag in ["fr", "fr-FR", "fr_CA.UTF-8", "FR_be", "fr@euro"] {
            assert_eq!(lang_of_tag(tag), Lang::Fr, "{tag}");
        }
        for tag in [
            "en-US",
            "en_GB.UTF-8",
            "de-DE",
            "C",
            "POSIX",
            "",
            "fra",
            "fy_NL",
        ] {
            assert_eq!(lang_of_tag(tag), Lang::En, "{tag}");
        }
    }

    #[test]
    fn linux_reads_lc_all_then_lc_messages_then_lang() {
        let env = |pairs: &'static [(&'static str, &'static str)]| {
            move |name: &str| {
                pairs
                    .iter()
                    .find(|(key, _)| *key == name)
                    .map(|(_, value)| value.to_string())
            }
        };
        assert_eq!(lang_of_env(env(&[("LANG", "fr_FR.UTF-8")])), Lang::Fr);
        assert_eq!(
            lang_of_env(env(&[
                ("LANG", "fr_FR.UTF-8"),
                ("LC_MESSAGES", "en_US.UTF-8")
            ])),
            Lang::En
        );
        assert_eq!(
            lang_of_env(env(&[
                ("LANG", "en_US.UTF-8"),
                ("LC_MESSAGES", "fr_FR.UTF-8")
            ])),
            Lang::Fr
        );
        assert_eq!(
            lang_of_env(env(&[
                ("LC_ALL", "fr_FR.UTF-8"),
                ("LC_MESSAGES", "en_US.UTF-8")
            ])),
            Lang::Fr
        );
        assert_eq!(
            lang_of_env(env(&[("LC_ALL", ""), ("LANG", "fr_FR.UTF-8")])),
            Lang::Fr
        );
        assert_eq!(lang_of_env(env(&[])), Lang::En);
    }

    #[test]
    fn the_system_language_is_read_from_the_os() {
        // Whatever this machine's language, reading it works and gives one of the two.
        let lang = system_lang();
        assert!(Lang::ALL.contains(&lang));
        assert_eq!(resolve(Language::System), lang);
    }

    #[test]
    fn a_forced_language_ignores_the_system() {
        assert_eq!(resolve(Language::French), Lang::Fr);
        assert_eq!(resolve(Language::English), Lang::En);
        assert_eq!(
            Language::ALL.map(Language::as_config),
            ["system", "fr", "en"]
        );
        assert_eq!(Language::from_config("fr"), Some(Language::French));
        assert_eq!(Language::from_config("de"), None);
    }

    #[test]
    fn fill_replaces_every_placeholder() {
        assert_eq!(
            fill_in(Lang::Fr, Text::UpdateAvailable, &[("version", "2.6.0")]),
            "Mise à jour disponible (2.6.0)"
        );
        assert_eq!(
            fill_in(Lang::En, Text::MenuHeader, &[("version", "2.6.0")]),
            "Whispy 2.6.0 \u{b7} voice dictation"
        );
    }
}

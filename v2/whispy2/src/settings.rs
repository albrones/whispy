//! V1's settings file, read and written by V2: the same `~/.config/whispy/config.json`,
//! the same keys, the same defaults, so a choice made in one app carries to the other.
//!
//! V2 owns three keys (`copy_to_clipboard`, `trigger_mode`, `trigger`). The file
//! holds many more (V1's `max_chunk_s`, `vocabulary`, `start_at_login`, ...):
//! [`save_key`] therefore never writes a model of the file, it re-reads the file,
//! changes the one key and writes everything else back as it found it.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use whispy_core::json::{parse_json, Json};

/// How the trigger drives a dictation: held for its whole length, or pressed
/// once to start and once to stop. V1's `trigger_mode` choices.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TriggerMode {
    Hold,
    Toggle,
}

impl TriggerMode {
    /// The value V1 stores in `trigger_mode`.
    pub fn as_config(self) -> &'static str {
        match self {
            TriggerMode::Hold => "hold",
            TriggerMode::Toggle => "toggle",
        }
    }
}

/// The key that starts a dictation: a macOS virtual keycode and the name shown to the user.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Trigger {
    pub keycode: i64,
    pub label: String,
}

/// The keycode of Fn / Globe, V1's default (`trigger: null`).
pub const FN_KEYCODE: i64 = 63;

impl Trigger {
    pub fn fn_key() -> Trigger {
        Trigger {
            keycode: FN_KEYCODE,
            label: "Fn".to_string(),
        }
    }

    /// The `trigger` value V1 stores for it: `null` for Fn, else the keycode.
    pub fn as_config(&self) -> Json {
        if self.keycode == FN_KEYCODE {
            Json::Null
        } else {
            Json::Int(self.keycode)
        }
    }

    fn from_keycode(keycode: i64) -> Trigger {
        let label = match keycode {
            FN_KEYCODE => "Fn".to_string(),
            54 => "Right Command".to_string(),
            61 => "Right Option".to_string(),
            105 => "F13".to_string(),
            other => key_name(other).map_or_else(|| format!("Key {other}"), str::to_string),
        };
        Trigger { keycode, label }
    }
}

/// V1's `TRIGGER_PRESETS`, in the order of its menu: what the Trigger submenu offers.
pub fn trigger_presets() -> Vec<Trigger> {
    [FN_KEYCODE, 54, 61, 105]
        .into_iter()
        .map(Trigger::from_keycode)
        .collect()
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Settings {
    pub copy_to_clipboard: bool,
    pub trigger_mode: TriggerMode,
    pub trigger: Trigger,
}

impl Default for Settings {
    /// V1's defaults.
    fn default() -> Settings {
        Settings {
            copy_to_clipboard: true,
            trigger_mode: TriggerMode::Hold,
            trigger: Trigger::fn_key(),
        }
    }
}

/// `~/.config/whispy/config.json`, the path V1 uses.
pub fn default_path() -> Option<PathBuf> {
    let home = std::env::var_os("HOME")?;
    Some(PathBuf::from(home).join(".config/whispy/config.json"))
}

/// The settings in `path`. Never fails: a missing or broken file, or a value V1
/// would reject, gives that key's default and a note for the log. Notes are
/// plain sentences, one per problem.
pub fn load(path: &Path) -> (Settings, Vec<String>) {
    let mut settings = Settings::default();
    let mut notes = Vec::new();
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) => {
            notes.push(format!(
                "settings file {} could not be read ({error}); using the defaults",
                path.display()
            ));
            return (settings, notes);
        }
    };
    let root = match parse_json(&text) {
        Ok(root @ Json::Object(_)) => root,
        Ok(_) => {
            notes.push(format!(
                "settings file {} is not a JSON object; using the defaults",
                path.display()
            ));
            return (settings, notes);
        }
        Err(error) => {
            notes.push(format!(
                "settings file {} could not be used ({error}); using the defaults",
                path.display()
            ));
            return (settings, notes);
        }
    };
    // An absent key is V1's default without a note; a present one that fails is a note.
    if let Some(value) = root.get("copy_to_clipboard") {
        match value.bool() {
            Some(copy) => settings.copy_to_clipboard = copy,
            None => notes.push("copy_to_clipboard is not true or false; using true".to_string()),
        }
    }
    if let Some(value) = root.get("trigger_mode") {
        match value.text() {
            Some("hold") => settings.trigger_mode = TriggerMode::Hold,
            Some("toggle") => settings.trigger_mode = TriggerMode::Toggle,
            _ => notes.push("trigger_mode is not \"hold\" or \"toggle\"; using hold".to_string()),
        }
    }
    if let Some(value) = root.get("trigger") {
        match value {
            Json::Null => {}
            Json::Int(keycode) if *keycode >= 0 => {
                settings.trigger = Trigger::from_keycode(*keycode)
            }
            Json::Text(text) if !text.trim().is_empty() => {
                notes.push("Trigger combinations are not supported yet; using Fn".to_string())
            }
            _ => notes.push("trigger is not null, a keycode or a key name; using Fn".to_string()),
        }
    }
    (settings, notes)
}

/// Sets `key` to `value` in the file at `path` and leaves everything else in it
/// as it was, in the same order. Refuses (`Err`, file untouched) when the file
/// exists but cannot be read or is not a JSON object: overwriting it would throw
/// away what the user keeps there. A missing file starts from an empty object.
///
/// The write goes to `config.json.tmp` (0600) and is renamed over the file, in a
/// 0700 directory, as V1's `save_config` does.
pub fn save_key(path: &Path, key: &str, value: Json) -> Result<(), String> {
    let mut fields = match fs::read_to_string(path) {
        Ok(text) => match parse_json(&text) {
            Ok(Json::Object(fields)) => fields,
            Ok(_) => return Err(format!("{} is not a JSON object", path.display())),
            Err(error) => return Err(format!("{} is not valid JSON ({error})", path.display())),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(error) => return Err(format!("{} could not be read ({error})", path.display())),
    };
    match fields.iter_mut().find(|(name, _)| name == key) {
        Some((_, slot)) => *slot = value,
        None => fields.push((key.to_string(), value)),
    }
    let text = Json::Object(fields).to_pretty_string();

    let directory = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(directory)
        .map_err(|error| format!("{} could not be created ({error})", directory.display()))?;
    set_mode(directory, 0o700);
    let tmp = path.with_extension("json.tmp");
    let written = write_private(&tmp, text.as_bytes()).and_then(|()| fs::rename(&tmp, path));
    if let Err(error) = written {
        let _ = fs::remove_file(&tmp);
        return Err(format!("{} could not be written ({error})", path.display()));
    }
    Ok(())
}

/// Creates `path` readable by its owner only, from the first byte: no window in
/// which the file exists with a wider mode.
fn write_private(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    // A leftover from a crashed save keeps its old mode otherwise.
    let _ = fs::remove_file(path);
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    let mut file = options.open(path)?;
    file.write_all(bytes)?;
    file.sync_all()
}

/// Best effort, like V1: a directory the user does not own cannot be chmod-ed,
/// and that is not a reason to refuse the save.
fn set_mode(path: &Path, mode: u32) {
    #[cfg(unix)]
    {
        let _ = fs::set_permissions(path, std::os::unix::fs::PermissionsExt::from_mode(mode));
    }
    #[cfg(not(unix))]
    let _ = (path, mode);
}

/// V1's `keycode_to_name` table (`hardware/event_decode.py`, the kVK_ values).
fn key_name(keycode: i64) -> Option<&'static str> {
    Some(match keycode {
        0 => "a",
        11 => "b",
        8 => "c",
        2 => "d",
        14 => "e",
        3 => "f",
        5 => "g",
        4 => "h",
        34 => "i",
        38 => "j",
        40 => "k",
        37 => "l",
        46 => "m",
        45 => "n",
        31 => "o",
        35 => "p",
        12 => "q",
        15 => "r",
        1 => "s",
        17 => "t",
        32 => "u",
        9 => "v",
        13 => "w",
        7 => "x",
        16 => "y",
        6 => "z",
        29 => "0",
        18 => "1",
        19 => "2",
        20 => "3",
        21 => "4",
        23 => "5",
        22 => "6",
        26 => "7",
        28 => "8",
        25 => "9",
        27 => "-",
        24 => "=",
        33 => "[",
        30 => "]",
        42 => "\\",
        41 => ";",
        39 => "'",
        43 => ",",
        47 => ".",
        44 => "/",
        50 => "`",
        36 => "enter",
        48 => "tab",
        49 => "space",
        51 => "backspace",
        53 => "escape",
        117 => "delete",
        114 => "help",
        55 => "command",
        56 => "shift",
        60 => "right_shift",
        58 => "option",
        59 => "control",
        62 => "right_control",
        57 => "caps_lock",
        122 => "f1",
        120 => "f2",
        99 => "f3",
        118 => "f4",
        96 => "f5",
        97 => "f6",
        98 => "f7",
        100 => "f8",
        101 => "f9",
        109 => "f10",
        103 => "f11",
        111 => "f12",
        107 => "f14",
        113 => "f15",
        106 => "f16",
        64 => "f17",
        79 => "f18",
        80 => "f19",
        90 => "f20",
        123 => "left",
        124 => "right",
        125 => "down",
        126 => "up",
        115 => "home",
        119 => "end",
        116 => "page_up",
        121 => "page_down",
        72 => "volume_up",
        73 => "volume_down",
        74 => "mute",
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    /// A fresh directory per test; `config.json` inside it is the file under test.
    fn scratch() -> PathBuf {
        static NEXT: AtomicU32 = AtomicU32::new(0);
        let directory = std::env::temp_dir().join(format!(
            "whispy2-settings-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        directory.join("config.json")
    }

    const V1_FILE: &str = r#"{
  "_version": 3,
  "copy_to_clipboard": true,
  "trigger_mode": "hold",
  "trigger": null,
  "max_chunk_s": 0.3,
  "vocabulary": ["Zénika", "naïve"],
  "start_at_login": true
}"#;

    #[test]
    fn v1_choices_are_picked_up() {
        let path = scratch();
        fs::write(
            &path,
            r#"{"trigger_mode": "toggle", "trigger": 61, "copy_to_clipboard": true}"#,
        )
        .unwrap();
        let (settings, notes) = load(&path);
        assert_eq!(settings.trigger_mode, TriggerMode::Toggle);
        assert_eq!(settings.trigger.keycode, 61);
        assert_eq!(settings.trigger.label, "Right Option");
        assert!(settings.copy_to_clipboard);
        assert!(notes.is_empty(), "{notes:?}");
    }

    #[test]
    fn a_broken_file_gives_the_defaults_and_a_note() {
        let path = scratch();
        fs::write(&path, r#"{"trigger_mode": "sometimes""#).unwrap();
        let (settings, notes) = load(&path);
        assert_eq!(settings, Settings::default());
        assert_eq!(notes.len(), 1);
        assert!(notes[0].contains("could not be used"), "{notes:?}");
    }

    #[test]
    fn a_missing_file_gives_the_defaults_and_a_note() {
        let (settings, notes) = load(&scratch());
        assert_eq!(settings, Settings::default());
        assert_eq!(notes.len(), 1);
    }

    #[test]
    fn defaults_are_v1s() {
        let defaults = Settings::default();
        assert!(defaults.copy_to_clipboard);
        assert_eq!(defaults.trigger_mode, TriggerMode::Hold);
        assert_eq!(defaults.trigger, Trigger::fn_key());
        assert_eq!(defaults.trigger.keycode, 63);
    }

    #[test]
    fn each_bad_value_falls_back_on_its_own_with_a_note() {
        let path = scratch();
        fs::write(
            &path,
            r#"{"copy_to_clipboard": "yes", "trigger_mode": 3, "trigger": 1.5}"#,
        )
        .unwrap();
        let (settings, notes) = load(&path);
        assert_eq!(settings, Settings::default());
        assert_eq!(notes.len(), 3, "{notes:?}");
        // A bool is not a keycode, a negative number is not one either.
        fs::write(&path, r#"{"trigger": true}"#).unwrap();
        assert_eq!(load(&path).1.len(), 1);
        fs::write(&path, r#"{"trigger": -1, "copy_to_clipboard": false}"#).unwrap();
        let (settings, notes) = load(&path);
        assert!(!settings.copy_to_clipboard);
        assert_eq!(notes.len(), 1);
        fs::write(&path, "[1]").unwrap();
        assert_eq!(load(&path).0, Settings::default());
    }

    #[test]
    fn trigger_values_map_to_keycodes_and_labels() {
        let path = scratch();
        for (json, keycode, label) in [
            ("null", 63, "Fn"),
            ("54", 54, "Right Command"),
            ("105", 105, "F13"),
            ("107", 107, "f14"),
            ("999", 999, "Key 999"),
        ] {
            fs::write(&path, format!(r#"{{"trigger": {json}}}"#)).unwrap();
            let (settings, notes) = load(&path);
            assert_eq!(
                (settings.trigger.keycode, settings.trigger.label.as_str()),
                (keycode, label)
            );
            assert!(notes.is_empty());
        }
    }

    #[test]
    fn a_trigger_combination_falls_back_to_fn_with_a_note() {
        let path = scratch();
        fs::write(&path, r#"{"trigger": "ctrl+alt+cmd+e"}"#).unwrap();
        let (settings, notes) = load(&path);
        assert_eq!(settings.trigger, Trigger::fn_key());
        assert_eq!(
            notes,
            ["Trigger combinations are not supported yet; using Fn"]
        );
    }

    #[test]
    fn presets_follow_v1s_menu_order() {
        let labels: Vec<String> = trigger_presets().into_iter().map(|t| t.label).collect();
        assert_eq!(labels, ["Fn", "Right Command", "Right Option", "F13"]);
        assert_eq!(Trigger::fn_key().as_config(), Json::Null);
        assert_eq!(Trigger::from_keycode(61).as_config(), Json::Int(61));
    }

    #[test]
    fn saving_a_key_keeps_v1_only_keys_with_their_exact_values() {
        let path = scratch();
        fs::write(&path, V1_FILE).unwrap();
        save_key(&path, "trigger_mode", Json::Text("toggle".into())).unwrap();
        let saved = parse_json(&fs::read_to_string(&path).unwrap()).unwrap();
        let before = parse_json(V1_FILE).unwrap();
        assert_eq!(
            saved.get("trigger_mode"),
            Some(&Json::Text("toggle".to_string()))
        );
        for key in ["max_chunk_s", "vocabulary", "start_at_login", "_version"] {
            assert_eq!(saved.get(key), before.get(key), "{key}");
        }
        assert_eq!(saved.get("max_chunk_s"), Some(&Json::Number(0.3)));
        let (Json::Object(saved_fields), Json::Object(before_fields)) = (&saved, &before) else {
            panic!("objects expected");
        };
        let order = |fields: &Vec<(String, Json)>| -> Vec<String> {
            fields.iter().map(|(key, _)| key.clone()).collect()
        };
        assert_eq!(order(saved_fields), order(before_fields));
        assert!(load(&path).1.is_empty());
        assert_eq!(load(&path).0.trigger_mode, TriggerMode::Toggle);
    }

    #[test]
    fn saving_a_new_key_appends_it_and_a_missing_file_is_created() {
        let path = scratch();
        save_key(&path, "copy_to_clipboard", Json::Bool(false)).unwrap();
        assert!(!load(&path).0.copy_to_clipboard);
        fs::write(&path, r#"{"a": 1}"#).unwrap();
        save_key(&path, "trigger", Json::Int(61)).unwrap();
        let saved = parse_json(&fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(saved.get("a"), Some(&Json::Int(1)));
        assert_eq!(saved.get("trigger"), Some(&Json::Int(61)));
    }

    #[test]
    fn an_unreadable_file_is_not_replaced() {
        let path = scratch();
        let broken = r#"{"trigger_mode": "sometimes", "vocabulary": ["Zénika""#;
        fs::write(&path, broken).unwrap();
        let error = save_key(&path, "copy_to_clipboard", Json::Bool(false)).unwrap_err();
        assert!(error.contains("not valid JSON"), "{error}");
        assert_eq!(fs::read(&path).unwrap(), broken.as_bytes());
        assert!(!path.with_extension("json.tmp").exists());
        // Valid JSON that is not an object is refused too.
        fs::write(&path, "[1, 2]").unwrap();
        assert!(save_key(&path, "a", Json::Null).is_err());
        assert_eq!(fs::read(&path).unwrap(), b"[1, 2]");
    }

    #[cfg(unix)]
    #[test]
    fn the_file_is_0600_and_no_temporary_is_left() {
        use std::os::unix::fs::PermissionsExt;
        let path = scratch();
        fs::write(&path, V1_FILE).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        // A stale temporary with a wide mode must not leak its mode.
        let tmp = path.with_extension("json.tmp");
        fs::write(&tmp, "stale").unwrap();
        fs::set_permissions(&tmp, fs::Permissions::from_mode(0o666)).unwrap();
        save_key(&path, "trigger", Json::Int(54)).unwrap();
        let mode = |p: &Path| fs::metadata(p).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode(&path), 0o600);
        assert_eq!(mode(path.parent().unwrap()), 0o700);
        assert!(!tmp.exists());
    }
}

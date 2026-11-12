//! The pure half of the menu's behaviour: what each status means for the menu,
//! what a menu action changes in the settings file, and how a restart is
//! scripted. `mac/menu_bar.rs` only renders and dispatches.

use std::path::Path;

use whispy_core::json::Json;

use crate::controller::{Status, LOADING_NOTE};
use crate::machine::State;
use crate::menu_model::{MenuAction, StatusFacts};
use crate::settings::{trigger_presets, Settings, Trigger, TriggerMode};

/// The facts V1's status line is chosen from. `trigger_down` is the live key
/// state: [`Status`] does not carry it, the tap callback reports it.
pub fn status_facts(status: &Status, trigger_down: bool) -> StatusFacts {
    StatusFacts {
        trigger_down,
        recording: matches!(status.state, State::Recording { .. }),
        transcribing: matches!(status.state, State::Transcribing { .. } | State::Inserting),
        // A load that failed leaves a different note: that is "Model not loaded".
        model_loading: !status.models_loaded && status.note.as_deref() == Some(LOADING_NOTE),
        model_loaded: status.models_loaded,
        yielded: matches!(status.state, State::Yielded),
    }
}

/// Whether the title waveform scrolls: recording, transcribing/inserting,
/// models loading, or the trigger held (V1's `_is_active`).
pub fn is_active(status: &Status, trigger_down: bool) -> bool {
    let facts = status_facts(status, trigger_down);
    facts.recording || facts.transcribing || facts.model_loading || facts.trigger_down
}

/// A settings change a menu action asks for.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Change {
    Copy(bool),
    Mode(TriggerMode),
    Trigger(Trigger),
}

impl Change {
    /// The config key it writes.
    pub fn key(&self) -> &'static str {
        match self {
            Change::Copy(_) => "copy_to_clipboard",
            Change::Mode(_) => "trigger_mode",
            Change::Trigger(_) => "trigger",
        }
    }

    /// The value V1 stores for it.
    pub fn value(&self) -> Json {
        match self {
            Change::Copy(copy) => Json::Bool(*copy),
            Change::Mode(mode) => Json::Text(mode.as_config().to_string()),
            Change::Trigger(trigger) => trigger.as_config(),
        }
    }

    pub fn apply(&self, settings: &mut Settings) {
        match self {
            Change::Copy(copy) => settings.copy_to_clipboard = *copy,
            Change::Mode(mode) => settings.trigger_mode = *mode,
            Change::Trigger(trigger) => settings.trigger = trigger.clone(),
        }
    }
}

/// What `action` changes given the `current` settings; `None` for actions that
/// are not settings (login, restart, quit, ...) or an unknown trigger.
pub fn change_for(action: MenuAction, current: &Settings) -> Option<Change> {
    match action {
        MenuAction::ToggleCopy => Some(Change::Copy(!current.copy_to_clipboard)),
        MenuAction::ToggleMode => Some(Change::Mode(match current.trigger_mode {
            TriggerMode::Hold => TriggerMode::Toggle,
            TriggerMode::Toggle => TriggerMode::Hold,
        })),
        MenuAction::SelectTrigger(value) => {
            let keycode = value.unwrap_or(crate::settings::FN_KEYCODE);
            trigger_presets()
                .into_iter()
                .find(|trigger| trigger.keycode == keycode)
                .map(Change::Trigger)
        }
        _ => None,
    }
}

/// The menu item tag of an action, and back: AppKit hands the action target
/// only the sender, whose tag says what was chosen.
pub fn action_tag(action: MenuAction) -> isize {
    match action {
        MenuAction::ToggleCopy => 1,
        MenuAction::ToggleMode => 2,
        MenuAction::ToggleLogin => 3,
        MenuAction::OpenPermissionSettings => 4,
        MenuAction::Restart => 5,
        MenuAction::Quit => 6,
        MenuAction::SelectTrigger(None) => 100,
        MenuAction::SelectTrigger(Some(keycode)) => 1000 + keycode as isize,
    }
}

pub fn tag_action(tag: isize) -> Option<MenuAction> {
    Some(match tag {
        1 => MenuAction::ToggleCopy,
        2 => MenuAction::ToggleMode,
        3 => MenuAction::ToggleLogin,
        4 => MenuAction::OpenPermissionSettings,
        5 => MenuAction::Restart,
        6 => MenuAction::Quit,
        100 => MenuAction::SelectTrigger(None),
        tag if tag >= 1000 => MenuAction::SelectTrigger(Some((tag - 1000) as i64)),
        _ => return None,
    })
}

/// What the restart relaunches.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Relaunch<'a> {
    /// The installed bundle, through `open`.
    Bundle(&'a Path),
    /// A bare executable (a cargo build), executed directly.
    Executable(&'a Path),
}

/// How long the waiter lets the old process free the socket: 50 x 0.1 s.
const WAIT_STEPS: u32 = 50;

/// The arguments of `/bin/sh` for a detached restart: wait until nothing
/// answers on the control socket (capped at 5 s), then start the new instance.
/// The paths are positional parameters, never part of the script text.
pub fn restart_command(socket: Option<&Path>, target: Relaunch) -> Vec<String> {
    let script = format!(
        "n=0; if [ -n \"$1\" ]; then while [ \"$n\" -lt {WAIT_STEPS} ] && \
         printf 'status\\n' | nc -w 1 -U \"$1\" >/dev/null 2>&1; do n=$((n+1)); sleep 0.1; done; fi; \
         if [ \"$3\" = open ]; then exec open \"$2\"; else exec \"$2\"; fi"
    );
    let (path, kind) = match target {
        Relaunch::Bundle(path) => (path, "open"),
        Relaunch::Executable(path) => (path, "exec"),
    };
    vec![
        "-c".to_string(),
        script,
        "whispy2-restart".to_string(),
        socket.map(|s| s.display().to_string()).unwrap_or_default(),
        path.display().to_string(),
        kind.to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    fn status(state: State, loaded: bool, note: Option<&str>) -> Status {
        Status {
            state,
            note: note.map(str::to_string),
            models_loaded: loaded,
            trigger_mode: TriggerMode::Hold,
            permission_pane: None,
        }
    }

    #[test]
    fn facts_follow_the_state_and_the_load() {
        let loading = status(State::Idle, false, Some(LOADING_NOTE));
        let facts = status_facts(&loading, false);
        assert!(facts.model_loading && !facts.model_loaded);
        let failed = status(State::Idle, false, Some("the model is missing"));
        assert!(!status_facts(&failed, false).model_loading);
        let now = Instant::now();
        let recording = status(
            State::Recording {
                mode: crate::machine::Mode::Hold,
                pressed_at: now,
                started_at: now,
            },
            true,
            None,
        );
        assert!(status_facts(&recording, false).recording);
        assert!(status_facts(&status(State::Inserting, true, None), false).transcribing);
        assert!(status_facts(&status(State::Yielded, true, None), false).yielded);
    }

    #[test]
    fn the_waveform_scrolls_only_when_something_is_happening() {
        assert!(!is_active(&status(State::Idle, true, None), false));
        assert!(is_active(&status(State::Idle, true, None), true));
        assert!(is_active(&status(State::Inserting, true, None), false));
        assert!(is_active(
            &status(State::Idle, false, Some(LOADING_NOTE)),
            false
        ));
        assert!(!is_active(
            &status(State::Idle, false, Some("failed")),
            false
        ));
    }

    #[test]
    fn actions_map_to_v1s_config_keys_and_values() {
        let settings = Settings::default();
        let copy = change_for(MenuAction::ToggleCopy, &settings).unwrap();
        assert_eq!(
            (copy.key(), copy.value()),
            ("copy_to_clipboard", Json::Bool(false))
        );
        let mode = change_for(MenuAction::ToggleMode, &settings).unwrap();
        assert_eq!(
            (mode.key(), mode.value()),
            ("trigger_mode", Json::Text("toggle".into()))
        );
        let right_command = change_for(MenuAction::SelectTrigger(Some(54)), &settings).unwrap();
        assert_eq!(
            (right_command.key(), right_command.value()),
            ("trigger", Json::Int(54))
        );
        let fn_key = change_for(MenuAction::SelectTrigger(None), &settings).unwrap();
        assert_eq!(fn_key.value(), Json::Null);
        assert!(change_for(MenuAction::Quit, &settings).is_none());
        assert!(change_for(MenuAction::SelectTrigger(Some(7)), &settings).is_none());
    }

    #[test]
    fn a_change_updates_the_settings_it_describes() {
        let mut settings = Settings::default();
        Change::Copy(false).apply(&mut settings);
        Change::Mode(TriggerMode::Toggle).apply(&mut settings);
        change_for(MenuAction::SelectTrigger(Some(61)), &settings)
            .unwrap()
            .apply(&mut settings);
        assert!(!settings.copy_to_clipboard);
        assert_eq!(settings.trigger_mode, TriggerMode::Toggle);
        assert_eq!(settings.trigger.keycode, 61);
        // Toggling again goes back.
        assert_eq!(
            change_for(MenuAction::ToggleMode, &settings),
            Some(Change::Mode(TriggerMode::Hold))
        );
    }

    #[test]
    fn tags_round_trip() {
        for action in [
            MenuAction::ToggleCopy,
            MenuAction::ToggleMode,
            MenuAction::ToggleLogin,
            MenuAction::OpenPermissionSettings,
            MenuAction::Restart,
            MenuAction::Quit,
            MenuAction::SelectTrigger(None),
            MenuAction::SelectTrigger(Some(54)),
            MenuAction::SelectTrigger(Some(105)),
        ] {
            assert_eq!(tag_action(action_tag(action)), Some(action));
        }
        assert_eq!(tag_action(0), None);
    }

    #[test]
    fn the_restart_waits_then_opens_the_bundle_or_runs_the_executable() {
        let bundle = restart_command(
            Some(Path::new("/tmp/a b.sock")),
            Relaunch::Bundle(Path::new("/Applications/Whispy V2.app")),
        );
        assert_eq!(bundle[0], "-c");
        assert_eq!(
            &bundle[3..],
            ["/tmp/a b.sock", "/Applications/Whispy V2.app", "open"]
        );
        assert!(bundle[1].contains("nc -w 1 -U"));
        let exe = restart_command(None, Relaunch::Executable(Path::new("/x/whispy2")));
        assert_eq!(&exe[3..], ["", "/x/whispy2", "exec"]);
    }

    #[test]
    fn the_restart_script_runs_the_target_after_the_wait() {
        let directory =
            std::env::temp_dir().join(format!("whispy2-restart-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let marker = directory.join("started");
        let target = directory.join("target.sh");
        std::fs::write(
            &target,
            format!("#!/bin/sh\ntouch '{}'\n", marker.display()),
        )
        .unwrap();
        std::fs::set_permissions(&target, std::os::unix::fs::PermissionsExt::from_mode(0o755))
            .unwrap();
        // Nothing listens on this socket: the wait ends at once.
        let args = restart_command(
            Some(&directory.join("none.sock")),
            Relaunch::Executable(&target),
        );
        let status = std::process::Command::new("/bin/sh")
            .args(&args)
            .status()
            .unwrap();
        assert!(status.success());
        assert!(marker.exists());
        let _ = std::fs::remove_dir_all(&directory);
    }
}

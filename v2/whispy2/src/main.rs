//! whispy2: the composition root. Wires the macOS adapters to the controller
//! and runs the AppKit loop on the main thread.

use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use objc2::MainThreadMarker;
use objc2_app_kit::{NSApplication, NSApplicationActivationPolicy};

use whispy2::control::{self, Claim, Control};
use whispy2::controller::{Controller, Input, LostClips, Source};
use whispy2::journal::Journal;
use whispy2::log;
use whispy2::mac::{
    inserter::{self, PasteInserter},
    menu_bar,
    microphone::Microphone,
    notify,
    pill::PillFeedback,
    trigger_tap,
};
use whispy2::machine::Event;
use whispy2::menu_model::Alert;
use whispy2::v1;

/// The watchdog's clock and the tap's health check.
const HOUSEKEEPING_PERIOD: Duration = Duration::from_secs(1);
/// How often V1 is looked for: a V1 started after V2 takes Fn back within this.
const V1_CHECK_EVERY: u32 = 2;

fn main() {
    let v2_dir = home().map(|home| home.join(".whispy/v2"));
    if let Some(directory) = &v2_dir {
        log::init(directory.clone());
    }
    // The trial counts these lines: a start that is neither a login nor a
    // reinstall is a relaunch to rescue the app (v2/TRIAL.md, criterion 5).
    log::line(&format!(
        "whispy2 started (version {}, pid {})",
        env!("CARGO_PKG_VERSION"),
        std::process::id()
    ));
    // One V2 per user, decided before anything else is started: a second launch
    // must not show a second icon or load the models twice.
    let control = match control::default_path().map(|path| control::claim(&path)) {
        Some(Ok(Claim::AlreadyRunning)) => {
            log::line("another Whispy V2 is already running; exiting");
            std::process::exit(0);
        }
        Some(Ok(Claim::Listening(control))) => Some(control),
        Some(Err(error)) => {
            log::line(&format!("the control socket is unavailable: {error}"));
            None
        }
        None => None,
    };
    let control: Rc<RefCell<Option<Control>>> = Rc::new(RefCell::new(control));
    let mtm = MainThreadMarker::new().expect("whispy2 must start on the main thread");
    let app = NSApplication::sharedApplication(mtm);
    // A menu bar app: no Dock icon, no main window.
    app.setActivationPolicy(NSApplicationActivationPolicy::Accessory);
    // Quit must free the models before `exit`: see `Controller::stop`.
    let running: Rc<RefCell<Option<Controller>>> = Rc::new(RefCell::new(None));
    let to_stop = Rc::clone(&running);
    let socket_to_remove = Rc::clone(&control);

    // Settings are read once, here: the menu keeps them current after that.
    let settings_path = whispy2::settings::default_path();
    let (settings, notes) = whispy2::settings::load(&settings_path.clone().unwrap_or_default());
    // Only the keys V2 owns are ever logged: the file holds other things.
    log::line(&format!(
        "settings: copy_to_clipboard={}, trigger_mode={}, trigger={}, type_while_speaking={}",
        settings.copy_to_clipboard,
        settings.trigger_mode.as_config(),
        whispy2::menu_model::trigger_label(settings.trigger.keycode),
        settings.type_while_speaking,
    ));
    for note in &notes {
        log::line(note);
    }
    let initial_mode = settings.trigger_mode;
    let initial_type_while_speaking = settings.type_while_speaking;
    let initial_keycode = settings.trigger.keycode;
    let settings = Rc::new(RefCell::new(settings));
    // Typed delivery is "copy to clipboard" off; shared so the menu can flip it live.
    let typed = Arc::new(AtomicBool::new(!settings.borrow().copy_to_clipboard));

    notify::request_authorization();
    inserter::warm_up();
    let controller = Controller::start(
        Microphone::new,
        whispy_core::Pipeline::load_default,
        PasteInserter::new(Arc::clone(&typed)),
        LostClips {
            directory: home().map(|home| home.join(".whispy/v2-lost")),
        },
        Journal {
            directory: v2_dir.clone(),
        },
        PillFeedback,
        |status| {
            match &status.note {
                Some(note) => log::line(&format!("{} ({note})", status.headline())),
                None => log::line(status.headline()),
            }
            menu_bar::show(status.clone());
        },
    );
    let inputs = controller.inputs.clone();
    if let Some(control) = control.borrow().as_ref() {
        let for_socket = inputs.clone();
        control.serve(move |request| control::dispatch(&for_socket, request));
    }

    // Before the first trigger event can arrive: V1 already running means the key is not ours.
    let mut is_v1_running = v1::is_running();
    controller.send(Event::V1Running(is_v1_running));
    // The configured trigger mode, also before the first trigger event.
    controller.send(Event::Settings(initial_mode));
    let _ = inputs.send(Input::TypeWhileSpeaking(initial_type_while_speaking));
    *running.borrow_mut() = Some(controller);

    let forward = inputs.clone();
    let trigger = trigger_tap::install(initial_keycode, move |event| {
        match &event {
            Event::TriggerDown(_) => menu_bar::set_trigger_down(true),
            Event::TriggerUp(_) => menu_bar::set_trigger_down(false),
            _ => {}
        }
        let _ = forward.send(Input::Event(event, Source::Fn));
    });
    let tap_health = match &trigger {
        Ok(trigger) => Some(trigger.health.clone()),
        Err(error) => {
            log::line(error);
            let _ = inputs.send(Input::Alert(Alert::missing_permission(
                "input_monitoring",
                error,
            )));
            None
        }
    };

    menu_bar::install(
        mtm,
        menu_bar::Handles {
            settings,
            settings_path,
            typed,
            trigger_key: trigger.as_ref().ok().map(|tap| tap.key.clone()),
            inputs: inputs.clone(),
            socket: control::default_path(),
        },
        move || {
            // `terminate:` exits without running destructors: remove the socket here.
            drop(socket_to_remove.borrow_mut().take());
            if let Some(controller) = to_stop.borrow_mut().take() {
                controller.stop();
            }
        },
    );

    thread::Builder::new()
        .name("whispy2-housekeeping".into())
        .spawn(move || {
            for beat in 1u32.. {
                thread::sleep(HOUSEKEEPING_PERIOD);
                let mut events = vec![Event::Tick(Instant::now())];
                if let Some(missed_release) = tap_health.as_ref().and_then(|health| health.revive())
                {
                    events.push(missed_release);
                }
                if beat % V1_CHECK_EVERY == 0 {
                    let is_running = v1::is_running();
                    if is_running != is_v1_running {
                        is_v1_running = is_running;
                        events.push(Event::V1Running(is_running));
                    }
                }
                for event in events {
                    if inputs.send(Input::Event(event, Source::Fn)).is_err() {
                        return;
                    }
                }
            }
        })
        .expect("the housekeeping thread could not be started");

    app.run();
    // `terminate:` exits inside `run`; this only runs if the loop ever returns.
    drop(trigger);
    drop(control.borrow_mut().take());
    let still_running = running.borrow_mut().take();
    if let Some(controller) = still_running {
        controller.stop();
    }
}

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

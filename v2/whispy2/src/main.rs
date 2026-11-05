//! whispy2: the composition root. Wires the macOS adapters to the controller
//! and runs the AppKit loop on the main thread.

use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;
use std::thread;
use std::time::{Duration, Instant};

use objc2::MainThreadMarker;
use objc2_app_kit::{NSApplication, NSApplicationActivationPolicy};

use whispy2::control::{self, Claim, Control};
use whispy2::controller::{Controller, Input, LostClips, Source};
use whispy2::journal::Journal;
use whispy2::log;
use whispy2::mac::{
    fn_key,
    indicator::PanelFeedback,
    inserter::{self, PasteInserter},
    menu_bar,
    microphone::Microphone,
};
use whispy2::machine::Event;
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
    menu_bar::install(mtm, move || {
        // `terminate:` exits without running destructors: remove the socket here.
        drop(socket_to_remove.borrow_mut().take());
        if let Some(controller) = to_stop.borrow_mut().take() {
            controller.stop();
        }
    });

    inserter::warm_up();
    let controller = Controller::start(
        Microphone::new,
        whispy_core::Pipeline::load_default,
        PasteInserter,
        LostClips {
            directory: home().map(|home| home.join(".whispy/v2-lost")),
        },
        Journal {
            directory: v2_dir.clone(),
        },
        PanelFeedback,
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

    // Before the first Fn event can arrive: V1 already running means Fn is not ours.
    let mut is_v1_running = v1::is_running();
    controller.send(Event::V1Running(is_v1_running));
    *running.borrow_mut() = Some(controller);

    let forward = inputs.clone();
    let fn_key = fn_key::install(move |event| {
        let _ = forward.send(Input::Event(event, Source::Fn));
    });
    let tap_health = match &fn_key {
        Ok(fn_key) => Some(fn_key.health.clone()),
        Err(error) => {
            log::line(error);
            let _ = inputs.send(Input::Note(error.clone()));
            None
        }
    };

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
    drop(fn_key);
    drop(control.borrow_mut().take());
    let still_running = running.borrow_mut().take();
    if let Some(controller) = still_running {
        controller.stop();
    }
}

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

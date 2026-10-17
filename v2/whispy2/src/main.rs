//! whispy2: the composition root. Wires the macOS adapters to the controller
//! and runs the AppKit loop on the main thread.

use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;
use std::thread;
use std::time::{Duration, Instant};

use objc2::MainThreadMarker;
use objc2_app_kit::{NSApplication, NSApplicationActivationPolicy};

use whispy2::controller::{Controller, Input, LostClips};
use whispy2::mac::{fn_key, inserter::PasteInserter, menu_bar, microphone::Microphone};
use whispy2::machine::Event;
use whispy2::v1;

/// The watchdog's clock and the tap's health check.
const HOUSEKEEPING_PERIOD: Duration = Duration::from_secs(1);
/// How often V1 is looked for: a V1 started after V2 takes Fn back within this.
const V1_CHECK_EVERY: u32 = 2;

fn main() {
    let mtm = MainThreadMarker::new().expect("whispy2 must start on the main thread");
    let app = NSApplication::sharedApplication(mtm);
    // A menu bar app: no Dock icon, no main window.
    app.setActivationPolicy(NSApplicationActivationPolicy::Accessory);
    // Quit must free the models before `exit`: see `Controller::stop`.
    let running: Rc<RefCell<Option<Controller>>> = Rc::new(RefCell::new(None));
    let to_stop = Rc::clone(&running);
    menu_bar::install(mtm, move || {
        if let Some(controller) = to_stop.borrow_mut().take() {
            controller.stop();
        }
    });

    let controller = Controller::start(
        Microphone::new,
        whispy_core::Pipeline::load_default,
        PasteInserter,
        LostClips {
            directory: home().map(|home| home.join(".whispy/v2-lost")),
        },
        |status| {
            // The terminal that launched whispy2 is its log.
            match &status.note {
                Some(note) => eprintln!("[whispy2] {} ({note})", status.headline()),
                None => eprintln!("[whispy2] {}", status.headline()),
            }
            menu_bar::show(status.clone());
        },
    );
    let inputs = controller.inputs.clone();

    // Before the first Fn event can arrive: V1 already running means Fn is not ours.
    let mut is_v1_running = v1::is_running();
    controller.send(Event::V1Running(is_v1_running));
    *running.borrow_mut() = Some(controller);

    let forward = inputs.clone();
    let fn_key = fn_key::install(move |event| {
        let _ = forward.send(Input::Event(event));
    });
    let tap_health = match &fn_key {
        Ok(fn_key) => Some(fn_key.health.clone()),
        Err(error) => {
            eprintln!("[whispy2] {error}");
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
                    if inputs.send(Input::Event(event)).is_err() {
                        return;
                    }
                }
            }
        })
        .expect("the housekeeping thread could not be started");

    app.run();
    // `terminate:` exits inside `run`; this only runs if the loop ever returns.
    drop(fn_key);
    let still_running = running.borrow_mut().take();
    if let Some(controller) = still_running {
        controller.stop();
    }
}

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

//! The Linux composition root: the controller with the cpal microphone and
//! the enigo inserter; the trigger key under X11, the compositor's binding
//! (through the control socket) under Wayland; the tray icon under X11.
//!
//! The main thread only waits for Quit (the icon's menu). No port is opened:
//! the control socket is the only way in.

use std::path::PathBuf;
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use super::inserter::EnigoInserter;
use super::notify;
use super::session::Session;
use super::surface::Surface;
use super::{tray, x11_trigger};
use crate::control::{self, Claim};
use crate::controller::{Controller, Input, LostClips, Source};
use crate::journal::Journal;
use crate::log;
use crate::machine::Event;
use crate::menu_model::Alert;
use crate::microphone::Microphone;
use crate::v1;

/// The watchdog's clock.
const HOUSEKEEPING_PERIOD: Duration = Duration::from_secs(1);
/// How often V1 is looked for: a V1 started after V2 takes the key back within this.
const V1_CHECK_EVERY: u32 = 2;

pub fn run() {
    let v2_dir = home().map(|home| home.join(".whispy/v2"));
    if let Some(directory) = &v2_dir {
        log::init(directory.clone());
    }
    let session = Session::current();
    log::line(&format!(
        "whispy2 started (version {}, pid {}, Linux, {} session)",
        env!("CARGO_PKG_VERSION"),
        std::process::id(),
        session.name()
    ));
    // One V2 per user, decided before anything else is started.
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

    let settings_path = crate::settings::default_path();
    let (settings, notes) = crate::settings::load(&settings_path.unwrap_or_default());
    log::line(&format!(
        "settings: trigger_mode={}, type_while_speaking={} (Linux types the text; the trigger key is {} under X11)",
        settings.trigger_mode.as_config(),
        settings.type_while_speaking,
        x11_trigger::TRIGGER_NAME,
    ));
    for note in notes.iter().filter(|note| !note.contains("using Fn")) {
        log::line(note);
    }

    // The icon first: the controller's feedback and status go through it.
    let (quit, quit_requested) = mpsc::channel::<()>();
    let tray = match session {
        Session::X11 => match tray::spawn(quit.clone()) {
            Ok(handle) => Some(handle),
            Err(reason) => {
                log::line(&format!(
                    "tray icon unavailable ({reason}); running with notifications only"
                ));
                notify::post(&Alert::tray_unavailable(&reason));
                None
            }
        },
        Session::Wayland | Session::None => None,
    };
    let surface = Surface::new(tray);
    let status_surface = surface.clone();

    let controller = Controller::start(
        Microphone::new,
        || crate::controller::load_models(notify::post),
        EnigoInserter::new(session),
        LostClips {
            directory: home().map(|home| home.join(".whispy/v2-lost")),
        },
        Journal {
            directory: v2_dir.clone(),
        },
        surface,
        move |status| {
            match &status.note {
                Some(note) => log::line(&format!("{} ({note})", status.headline())),
                None => log::line(status.headline()),
            }
            status_surface.status(status);
        },
    );
    let inputs = controller.inputs.clone();
    if let Some(control) = control.as_ref() {
        let for_socket = inputs.clone();
        control.serve(move |request| control::dispatch(&for_socket, request));
    }

    let mut is_v1_running = v1::is_running();
    controller.send(Event::V1Running(is_v1_running));
    controller.send(Event::Settings(settings.trigger_mode));
    let _ = inputs.send(Input::TypeWhileSpeaking(settings.type_while_speaking));

    match session {
        Session::X11 => {
            let forward = inputs.clone();
            let lost = inputs.clone();
            let listening = x11_trigger::listen(
                move |event| {
                    let _ = forward.send(Input::Event(event, Source::Fn));
                },
                move |message| {
                    log::line(&message);
                    let _ = lost.send(Input::Alert(Alert::trigger_key_unavailable(&message)));
                },
            );
            if let Err(message) = listening {
                log::line(&message);
                let _ = inputs.send(Input::Alert(Alert::trigger_key_unavailable(&message)));
            }
        }
        Session::Wayland => log::line(
            "Wayland: no key is listened to; the compositor's key binding drives the control socket",
        ),
        Session::None => log::line(
            "no graphical session: no key is listened to and text cannot be typed; the control socket still answers",
        ),
    }

    let housekeeping = inputs.clone();
    thread::Builder::new()
        .name("whispy2-housekeeping".into())
        .spawn(move || {
            for beat in 1u32.. {
                thread::sleep(HOUSEKEEPING_PERIOD);
                let mut events = vec![Event::Tick(Instant::now())];
                if beat % V1_CHECK_EVERY == 0 {
                    let is_running = v1::is_running();
                    if is_running != is_v1_running {
                        is_v1_running = is_running;
                        events.push(Event::V1Running(is_running));
                    }
                }
                for event in events {
                    if housekeeping.send(Input::Event(event, Source::Fn)).is_err() {
                        return;
                    }
                }
            }
        })
        .expect("the housekeeping thread could not be started");

    // Only the icon's Quit ends the wait (`quit` stays alive here, so it never
    // disconnects); SIGTERM from `systemd` ends the process directly, and the
    // next start replaces the socket nobody answers on.
    let _ = quit_requested.recv();
    log::line("quit requested");
    drop(quit);
    drop(control);
    controller.stop();
    std::process::exit(0);
}

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

//! The local control socket: how scripts, tests and, later, a compositor key
//! binding drive V2, and the lock that keeps one V2 per user.
//!
//! A Unix socket at `~/.whispy/v2/control.sock` (`WHISPY_V2_SOCKET` overrides),
//! in a 0700 directory: the directory is the real guard, since permissions on a
//! socket file are not honoured alike on BSD and Linux. No TCP port is opened.
//! Line protocol, one request and one reply line per connection: `start`,
//! `stop`, `toggle`, `status`, `last`, `check-update`, `update`. The Omarchy
//! bar panel reads `status` (which carries the input level and the update
//! row) and `last` straight from the socket, and sends the update row's request.
//!
//! The socket produces the events the trigger key produces and the machine never
//! learns where an edge came from: that is why a `stop` while idle, or a
//! `start` while recording, is ignored for free.
//!
//! The lock is "connect first": a V2 that answers means this process exits; a
//! refused connection means a crash left the file behind, so it is replaced.
//! Cheaper and more honest than a pid file, which has the same stale-file
//! problem and a second mechanism.

use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Sender};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use crate::controller::{Input, Live, Source, Status};
use crate::journal::json_string;
use crate::log;
use crate::machine::{Event, Mode, State, MIN_HOLD};
use crate::settings::TriggerMode;
use crate::update::{self, Row, Updater};

pub const SOCKET_ENV: &str = "WHISPY_V2_SOCKET";

/// A client that connects and says nothing must not hold a thread forever.
const READ_TIMEOUT: Duration = Duration::from_secs(2);
/// The controller answers a status query at once unless it is gone.
const QUERY_TIMEOUT: Duration = Duration::from_secs(2);
/// A request is one short word; anything longer is garbage.
const MAX_REQUEST: u64 = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Request {
    Start,
    Stop,
    Toggle,
    Status,
    /// The whole text of the last dictation, kept in memory only.
    Last,
    /// Checks for a newer release now, as the daily check does.
    CheckUpdate,
    /// « Update available (X.Y.Z) »: installs the offered version.
    Update,
}

pub fn parse(line: &str) -> Result<Request, String> {
    match line.trim() {
        "start" => Ok(Request::Start),
        "stop" => Ok(Request::Stop),
        "toggle" => Ok(Request::Toggle),
        "status" => Ok(Request::Status),
        "last" => Ok(Request::Last),
        "check-update" => Ok(Request::CheckUpdate),
        "update" => Ok(Request::Update),
        other => Err(format!(
            "error: unknown request {:?}; expected start, stop, toggle, status, last, check-update or update",
            other.chars().take(32).collect::<String>()
        )),
    }
}

/// `$WHISPY_V2_SOCKET`, else `~/.whispy/v2/control.sock`.
pub fn default_path() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os(SOCKET_ENV).filter(|path| !path.is_empty()) {
        return Some(PathBuf::from(path));
    }
    std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".whispy/v2/control.sock"))
}

/// The result of trying to become the one V2.
pub enum Claim {
    /// Another V2 answered; this process must exit without touching the socket.
    AlreadyRunning,
    Listening(Control),
}

/// A bound socket. Dropping it removes the socket file.
pub struct Control {
    listener: UnixListener,
    path: PathBuf,
}

/// Connects first, then binds (see the module docs for the three outcomes).
pub fn claim(path: &Path) -> std::io::Result<Claim> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        log::ensure_private_dir(parent)?;
    }
    match UnixStream::connect(path) {
        Ok(_) => return Ok(Claim::AlreadyRunning),
        Err(error) => match error.kind() {
            std::io::ErrorKind::NotFound => {}
            std::io::ErrorKind::ConnectionRefused => {
                log::line("control socket: replacing a socket no V2 answers on (a crash, or a quit that skipped the menu)");
            }
            _ => log::line(&format!(
                "control socket: probing {} failed ({error}); binding anyway",
                path.display()
            )),
        },
    }
    // Nothing answered, so whatever file is there is not a live V2's.
    let _ = std::fs::remove_file(path);
    let listener = UnixListener::bind(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    Ok(Claim::Listening(Control {
        listener,
        path: path.to_path_buf(),
    }))
}

impl Control {
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Starts the accept thread: one short-lived handler thread per connection,
    /// so a client that stalls cannot block the next. `handle` answers a request
    /// with its one reply line.
    pub fn serve(&self, handle: impl Fn(Request) -> String + Send + Sync + 'static) {
        let listener = match self.listener.try_clone() {
            Ok(listener) => listener,
            Err(error) => {
                log::line(&format!("control socket: cannot listen: {error}"));
                return;
            }
        };
        let handle = Arc::new(handle);
        let spawned = thread::Builder::new()
            .name("whispy2-control".into())
            .spawn(move || {
                for stream in listener.incoming() {
                    match stream {
                        Ok(stream) => {
                            let handle = Arc::clone(&handle);
                            let _ = thread::Builder::new()
                                .name("whispy2-control-conn".into())
                                .spawn(move || answer(stream, &*handle));
                        }
                        Err(error) => {
                            log::line(&format!("control socket: accept failed: {error}"));
                            thread::sleep(Duration::from_millis(100));
                        }
                    }
                }
            });
        if let Err(error) = spawned {
            log::line(&format!("control socket: cannot start its thread: {error}"));
        }
    }
}

impl Drop for Control {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

fn answer(stream: UnixStream, handle: &dyn Fn(Request) -> String) {
    let _ = stream.set_read_timeout(Some(READ_TIMEOUT));
    let mut line = String::new();
    // An instance probing the socket connects and hangs up: no request, no reply.
    match BufReader::new((&stream).take(MAX_REQUEST)).read_line(&mut line) {
        Ok(0) | Err(_) => return,
        Ok(_) => {}
    }
    let reply = match parse(&line) {
        Ok(request) => handle(request),
        Err(error) => error,
    };
    let _ = (&stream).write_all(format!("{reply}\n").as_bytes());
}

/// The client side, for `whispy2 send <request>`: one request, its reply line.
/// What the Omarchy dictation keys call, so they need no `socat` or `nc`.
pub fn send(path: &Path, request: &str) -> std::io::Result<String> {
    let mut stream = UnixStream::connect(path)?;
    stream.set_read_timeout(Some(SEND_TIMEOUT))?;
    stream.write_all(format!("{}\n", request.trim()).as_bytes())?;
    let mut reply = String::new();
    BufReader::new(&stream).read_line(&mut reply)?;
    Ok(reply.trim_end().to_string())
}

/// What `send` waits for a reply: a status query takes up to [`QUERY_TIMEOUT`].
const SEND_TIMEOUT: Duration = Duration::from_secs(5);

/// Whether a reply line reports a refusal or an error rather than an answer.
pub fn is_failure(reply: &str) -> bool {
    reply.starts_with("error") || reply.starts_with("refused")
}

/// Turns a request into controller inputs and its reply line.
///
/// `start` and `toggle` are refused while V2 yields to V1: the key belongs to
/// V1, and an ignored `start` would answer `ok` and record nothing. The status
/// is read first on the same channel, so it is ordered after any earlier request.
///
/// `check-update` and `update` act on `updater` (the menu's): `update` is
/// refused unless an update is offered.
pub fn dispatch(inputs: &Sender<Input>, updater: Option<&Updater>, request: Request) -> String {
    match (request, updater) {
        (Request::CheckUpdate, Some(updater)) => {
            updater.check();
            return "ok".into();
        }
        (Request::Update, Some(updater)) => {
            return if updater.install() {
                "ok".into()
            } else {
                "refused: no update is offered; check for updates first".into()
            };
        }
        (Request::CheckUpdate | Request::Update, None) => {
            return "refused: updates are not available in this build".into();
        }
        _ => {}
    }
    let Some(status) = query(inputs) else {
        return "error: V2 is shutting down".into();
    };
    let send = |event: Event| inputs.send(Input::Event(event, Source::Socket)).is_ok();
    match request {
        Request::Status => status_json(
            &status,
            live(inputs).unwrap_or_default().level,
            updater.and_then(Updater::row).as_ref(),
        ),
        Request::Last => last_json(live(inputs).and_then(|live| live.last_text).as_deref()),
        Request::Start | Request::Toggle if status.state == State::Yielded => {
            "refused: Whispy V1 is running and holds the trigger".into()
        }
        Request::Start => reply(send(Event::TriggerDown(Instant::now()))),
        Request::Stop => reply(send(Event::TriggerUp(release_stamp(
            status.state,
            Instant::now(),
        )))),
        Request::Toggle => reply(send_toggle(&status, &send)),
        Request::CheckUpdate | Request::Update => unreachable!("answered above"),
    }
}

/// One Toggle-mode press. In Toggle mode that is a single trigger press. In
/// Hold mode it starts when idle and stops when recording, as a hold would: a
/// press and release pair would be a short press, which Hold discards.
fn send_toggle(status: &Status, send: &dyn Fn(Event) -> bool) -> bool {
    let now = Instant::now();
    match (status.trigger_mode, status.state) {
        (TriggerMode::Toggle, _) => send(Event::TriggerDown(now)),
        (TriggerMode::Hold, State::Recording { .. }) => {
            send(Event::TriggerUp(release_stamp(status.state, now)))
        }
        (TriggerMode::Hold, _) => send(Event::TriggerDown(now)),
    }
}

fn reply(is_sent: bool) -> String {
    if is_sent {
        "ok".into()
    } else {
        "error: V2 is shutting down".into()
    }
}

/// When a socket `stop` counts as released. It must be a hold: a `stop` sent
/// right after a `start` (a script, a fast client) would otherwise look like a
/// tap, latch the recording into toggle mode and leave it running. So the
/// release is stamped no sooner than [`MIN_HOLD`] after the press. The machine
/// only compares event times, so a stamp slightly in the future is harmless,
/// and the recording ends right away: the recording stops when the event is
/// handled, not when its stamp comes due.
pub fn release_stamp(state: State, now: Instant) -> Instant {
    match state {
        State::Recording {
            mode: Mode::Hold,
            pressed_at,
            ..
        } => now.max(pressed_at + MIN_HOLD),
        _ => now,
    }
}

fn query(inputs: &Sender<Input>) -> Option<Status> {
    let (reply, answer) = mpsc::channel();
    inputs.send(Input::Query(reply)).ok()?;
    answer.recv_timeout(QUERY_TIMEOUT).ok()
}

fn live(inputs: &Sender<Input>) -> Option<Live> {
    let (reply, answer) = mpsc::channel();
    inputs.send(Input::Live(reply)).ok()?;
    answer.recv_timeout(QUERY_TIMEOUT).ok()
}

/// The `last` reply: `{"text":"…"}`, or `{"text":null}` before any dictation.
pub fn last_json(text: Option<&str>) -> String {
    match text {
        Some(text) => format!("{{\"text\":{}}}", json_string(text)),
        None => "{\"text\":null}".to_string(),
    }
}

/// The `status` reply: one line of JSON. `level` is the input level of the
/// recording (V1's scale, 0 when nothing records), for the Omarchy pill;
/// `update` the update row, for the Omarchy panel.
pub fn status_json(status: &Status, level: f32, update: Option<&Row>) -> String {
    let problem = match status.last_problem() {
        Some(problem) => json_string(problem),
        None => "null".to_string(),
    };
    format!(
        "{{\"state\":{},\"models_loaded\":{},\"yielded\":{},\"last_problem\":{problem},\"trigger_mode\":\"{}\",\"level\":{}{}}}",
        json_string(status.state_name()),
        status.models_loaded,
        status.state == State::Yielded,
        match status.trigger_mode {
            TriggerMode::Hold => "hold",
            TriggerMode::Toggle => "toggle",
        },
        json_number(level),
        match update {
            Some(row) => format!(",\"update\":{}", update::row_json(row)),
            None => String::new(),
        }
    )
}

/// A level as JSON: finite, never negative, three decimals.
fn json_number(level: f32) -> String {
    let level = if level.is_finite() {
        level.max(0.0)
    } else {
        0.0
    };
    format!("{level:.3}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::log::testing::temp_dir;
    use std::io::Read;

    fn ask(path: &Path, request: &str) -> String {
        let mut stream = UnixStream::connect(path).unwrap();
        stream.write_all(format!("{request}\n").as_bytes()).unwrap();
        let mut reply = String::new();
        stream.read_to_string(&mut reply).unwrap();
        reply.trim_end().to_string()
    }

    fn listening(path: &Path) -> Control {
        match claim(path).unwrap() {
            Claim::Listening(control) => control,
            Claim::AlreadyRunning => panic!("nothing should be listening on {}", path.display()),
        }
    }

    #[test]
    fn requests_parse_and_unknown_ones_are_errors() {
        assert_eq!(parse("start\n"), Ok(Request::Start));
        assert_eq!(parse(" stop "), Ok(Request::Stop));
        assert_eq!(parse("toggle"), Ok(Request::Toggle));
        assert_eq!(parse("status"), Ok(Request::Status));
        assert_eq!(parse("last"), Ok(Request::Last));
        assert_eq!(parse("check-update"), Ok(Request::CheckUpdate));
        assert_eq!(parse("update\n"), Ok(Request::Update));
        assert!(parse("record").unwrap_err().starts_with("error"));
        assert!(parse("").unwrap_err().starts_with("error"));
    }

    #[test]
    fn the_directory_is_private_and_so_is_the_socket() {
        let root = temp_dir("control-private");
        let path = root.join("v2/control.sock");
        let control = listening(&path);
        let mode = |path: &Path| std::fs::metadata(path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode(path.parent().unwrap()), 0o700);
        assert_eq!(mode(&path), 0o600);
        drop(control);
        assert!(!path.exists(), "the socket is removed on drop");
    }

    #[test]
    fn one_line_in_one_line_out_and_unknown_requests_are_errors() {
        let path = temp_dir("control-protocol").join("control.sock");
        let control = listening(&path);
        control.serve(|request| format!("{request:?}"));
        assert_eq!(ask(&path, "toggle"), "Toggle");
        assert!(ask(&path, "record").starts_with("error"));
    }

    #[test]
    fn send_asks_one_request_and_reads_its_reply() {
        let path = temp_dir("control-send").join("control.sock");
        let control = listening(&path);
        control.serve(|request| format!("{request:?}"));
        assert_eq!(send(&path, "last\n").unwrap(), "Last");
        assert!(is_failure(&send(&path, "record").unwrap()));
        assert!(!is_failure("ok") && is_failure("refused: Whispy V1 is running"));
        drop(control);
        assert!(
            send(&path, "status").is_err(),
            "nothing listens once dropped"
        );
    }

    #[test]
    fn a_second_instance_sees_the_first_and_leaves_its_socket_alone() {
        let path = temp_dir("control-single").join("control.sock");
        let first = listening(&path);
        first.serve(|_| "ok".into());
        assert!(matches!(claim(&path).unwrap(), Claim::AlreadyRunning));
        // The first keeps answering after the probe.
        assert_eq!(ask(&path, "status"), "ok");
    }

    #[test]
    fn a_stale_socket_is_replaced() {
        let path = temp_dir("control-stale").join("control.sock");
        // A crash leaves the file with nobody behind it.
        drop(UnixListener::bind(&path).unwrap());
        assert!(path.exists());
        let control = listening(&path);
        control.serve(|_| "ok".into());
        assert_eq!(ask(&path, "status"), "ok");
    }

    #[test]
    fn a_stop_right_after_a_start_still_counts_as_a_hold() {
        let now = Instant::now();
        let state = State::Recording {
            mode: Mode::Hold,
            pressed_at: now,
            started_at: now,
        };
        let stamp = release_stamp(state, now + Duration::from_millis(20));
        assert!(stamp.saturating_duration_since(now) >= MIN_HOLD);
        // A long hold keeps its own time; other states are untouched.
        let late = now + Duration::from_secs(2);
        assert_eq!(release_stamp(state, late), late);
        assert_eq!(release_stamp(State::Idle, now), now);
    }

    fn toggle_sent(mode: TriggerMode, state: State) -> Vec<Event> {
        let status = Status {
            state,
            note: None,
            models_loaded: true,
            trigger_mode: mode,
            permission_pane: None,
        };
        let sent = std::cell::RefCell::new(Vec::new());
        assert!(send_toggle(&status, &|event| {
            sent.borrow_mut().push(event);
            true
        }));
        sent.into_inner()
    }

    #[test]
    fn toggle_is_one_press_in_toggle_mode() {
        let sent = toggle_sent(TriggerMode::Toggle, State::Idle);
        assert!(matches!(sent.as_slice(), [Event::TriggerDown(_)]));
        let now = Instant::now();
        let recording = State::Recording {
            mode: Mode::Toggle,
            pressed_at: now,
            started_at: now,
        };
        let sent = toggle_sent(TriggerMode::Toggle, recording);
        assert!(matches!(sent.as_slice(), [Event::TriggerDown(_)]));
    }

    #[test]
    fn toggle_in_hold_mode_starts_when_idle_and_stops_as_a_hold_when_recording() {
        let sent = toggle_sent(TriggerMode::Hold, State::Idle);
        assert!(matches!(sent.as_slice(), [Event::TriggerDown(_)]));
        let now = Instant::now();
        let recording = State::Recording {
            mode: Mode::Hold,
            pressed_at: now,
            started_at: now,
        };
        let sent = toggle_sent(TriggerMode::Hold, recording);
        let [Event::TriggerUp(at)] = sent.as_slice() else {
            panic!("expected one release, got {sent:?}");
        };
        assert!(at.saturating_duration_since(now) >= MIN_HOLD);
    }

    #[test]
    fn status_is_one_line_of_json() {
        let status = Status {
            state: State::Idle,
            note: Some("Microphone heard nothing (\"Mic\")".into()),
            models_loaded: true,
            trigger_mode: TriggerMode::Hold,
            permission_pane: None,
        };
        assert_eq!(
            status_json(&status, 0.0, None),
            "{\"state\":\"idle\",\"models_loaded\":true,\"yielded\":false,\"last_problem\":\"Microphone heard nothing (\\\"Mic\\\")\",\"trigger_mode\":\"hold\",\"level\":0.000}"
        );
        let loading = Status {
            state: State::Yielded,
            note: Some(crate::controller::LOADING_NOTE.into()),
            models_loaded: false,
            trigger_mode: TriggerMode::Toggle,
            permission_pane: None,
        };
        let json = status_json(&loading, 0.4567, None);
        assert!(json.contains("\"yielded\":true") && json.contains("\"last_problem\":null"));
        assert!(json.contains("\"trigger_mode\":\"toggle\""));
        assert!(json.ends_with(",\"level\":0.457}"));
        assert!(status_json(&loading, f32::NAN, None).ends_with(",\"level\":0.000}"));
    }

    #[test]
    fn status_carries_the_update_row_for_the_panel() {
        let status = Status {
            state: State::Idle,
            note: None,
            models_loaded: true,
            trigger_mode: TriggerMode::Hold,
            permission_pane: None,
        };
        let row = Row {
            title: "Update available (2.5.0)".into(),
            enabled: true,
            transient: false,
        };
        assert!(status_json(&status, 0.0, Some(&row)).ends_with(
            ",\"level\":0.000,\"update\":{\"title\":\"Update available (2.5.0)\",\"action\":\"update\",\"transient\":false}}"
        ));
        // Up to date: no row, no `update` key.
        assert!(status_json(&status, 0.0, None).ends_with(",\"level\":0.000}"));
    }

    #[test]
    fn update_requests_reach_the_updater_and_update_needs_an_offer() {
        use crate::update::{Checked, Installed, Version};
        let (inputs, _unused) = mpsc::channel();
        let updater = Updater::with(
            Version(2, 4, 0),
            || Checked::Latest(Version(2, 5, 0)),
            |_| Installed::Done,
        );
        assert!(dispatch(&inputs, Some(&updater), Request::Update).starts_with("refused"));
        assert_eq!(
            dispatch(&inputs, Some(&updater), Request::CheckUpdate),
            "ok"
        );
        let deadline = Instant::now() + Duration::from_secs(5);
        while updater.row().is_none() {
            assert!(Instant::now() < deadline, "{:?}", updater.row());
            thread::sleep(Duration::from_millis(5));
        }
        assert_eq!(dispatch(&inputs, Some(&updater), Request::Update), "ok");
        assert!(dispatch(&inputs, None, Request::CheckUpdate).starts_with("refused"));
    }

    #[test]
    fn last_is_the_text_as_json_or_null() {
        assert_eq!(last_json(None), "{\"text\":null}");
        assert_eq!(
            last_json(Some("Il a dit \"oui\".\n")),
            "{\"text\":\"Il a dit \\\"oui\\\".\\n\"}"
        );
    }
}

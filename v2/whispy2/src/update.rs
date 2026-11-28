//! Updating Whispy from its menu: the macOS menu bar, the Linux tray icon and
//! the Omarchy bar panel (through the control socket).
//!
//! - **Check**: the last published version is the highest `vX.Y.Z` tag of the
//!   public repository, read with `git ls-remote --tags` (no API, no token).
//!   Whispy checks at startup, then once a day (and on the socket's
//!   `check-update`). At rest the row is a grey status line that cannot be
//!   chosen: « Whispy 2.6.0 · up to date » once a check found nothing newer,
//!   plain « Whispy 2.6.0 » before the first answer or offline (a failed
//!   check is only logged).
//! - **Offer**: when a newer version is published, the row « Update available
//!   (X.Y.Z) » appears. Finding it installs nothing: choosing it, a click of
//!   its own, does.
//! - **Install**: choosing the offer runs that tag's `scripts/bootstrap.sh`
//!   with `WHISPY_REF=vX.Y.Z`, detached from the app: the script rebuilds,
//!   replaces and restarts Whispy, so this process does not live to see it
//!   succeed. Under Linux it runs as a transient `systemd --user` unit: the
//!   restart of `whispy2.service` stops every process of the unit's cgroup,
//!   the script included otherwise. `WHISPY_UNATTENDED=1` makes the script
//!   stop with [`NEEDS_TERMINAL_EXIT`] rather than ask for a password (sudo),
//!   and the row then shows the command to run in a terminal. Every end the
//!   app lives to see is shown on the row: a failure with its reason (the
//!   last `[FAIL]` line of `~/.whispy/v2/update.log`), or an install that
//!   left this old process running.
//!
//! The pure half ([`Version`], [`latest_tag`], [`Updater`]'s transitions and
//! [`Row`]) is unit-tested with fake checks and installs.

use std::fmt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime};

use crate::log;

/// Every text the update shows, in one place, drawn from the translation
/// files (`i18n/*.json`, #64) in the language in force.
pub mod texts {
    use super::Version;
    use crate::i18n::{fill, Text};

    pub fn current(version: Version) -> String {
        fill(Text::UpdateCurrent, &[("version", &version.to_string())])
    }

    pub fn up_to_date(version: Version) -> String {
        fill(Text::UpdateUpToDate, &[("version", &version.to_string())])
    }

    pub fn available(version: Version) -> String {
        fill(Text::UpdateAvailable, &[("version", &version.to_string())])
    }

    pub fn updating_to(version: Version) -> String {
        fill(Text::UpdateUpdatingTo, &[("version", &version.to_string())])
    }

    pub fn update_failed(version: Version, reason: &str) -> String {
        fill(
            Text::UpdateFailed,
            &[("version", &version.to_string()), ("reason", reason)],
        )
    }

    pub fn not_restarted(version: Version) -> String {
        fill(
            Text::UpdateNotRestarted,
            &[("version", &version.to_string())],
        )
    }

    pub fn needs_terminal(command: &str) -> String {
        fill(Text::UpdateNeedsTerminal, &[("command", command)])
    }
}

/// The public repository the versions are read from.
pub const REPOSITORY: &str = "https://github.com/albrones/whispy.git";
/// Where a tag's files are served raw.
const RAW: &str = "https://raw.githubusercontent.com/albrones/whispy";
/// The exit code of `bootstrap.sh` under `WHISPY_UNATTENDED=1` when a step
/// would need sudo (or a dialog): nothing was changed.
pub const NEEDS_TERMINAL_EXIT: i32 = 3;
/// How long `git ls-remote` may take before the check counts as failed.
const CHECK_TIMEOUT: Duration = Duration::from_secs(20);
/// How often an automatic check is due.
const DAILY: Duration = Duration::from_secs(24 * 60 * 60);
/// How often the daily clock looks at the wall clock: a sleeping laptop does
/// not count down a monotonic sleep, the wall clock does.
const DAILY_POLL: Duration = Duration::from_secs(10 * 60);
/// The unit name of the Linux update, fixed so two updates cannot overlap.
const LINUX_UNIT: &str = "whispy2-update";

/// A release version, `X.Y.Z`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Version(pub u64, pub u64, pub u64);

impl Version {
    /// `2.4.0`, or a tag name `v2.4.0`. Anything else (`v2.4`, `v2.4.0-rc1`) is `None`.
    pub fn parse(text: &str) -> Option<Version> {
        let text = text.strip_prefix('v').unwrap_or(text);
        let mut parts = text.split('.');
        let mut next = || -> Option<u64> {
            let part = parts.next()?;
            if part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()) {
                return None;
            }
            part.parse().ok()
        };
        let version = Version(next()?, next()?, next()?);
        parts.next().is_none().then_some(version)
    }

    /// This build's version (Cargo.toml, stamped by each release).
    pub fn current() -> Version {
        Version::parse(env!("CARGO_PKG_VERSION")).expect("the crate version is X.Y.Z")
    }

    /// The tag that publishes it.
    pub fn tag(self) -> String {
        format!("v{self}")
    }
}

impl fmt::Display for Version {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}.{}", self.0, self.1, self.2)
    }
}

/// The highest `vX.Y.Z` tag in `git ls-remote --tags` output; other tags and
/// the peeled `^{}` lines are skipped.
pub fn latest_tag(ls_remote: &str) -> Option<Version> {
    ls_remote
        .lines()
        .filter_map(|line| line.split_whitespace().nth(1))
        .filter_map(|reference| reference.strip_prefix("refs/tags/"))
        .filter_map(Version::parse)
        .max()
}

/// The command a user runs in a terminal to install `version` by hand.
pub fn terminal_command(version: Version) -> String {
    format!(
        "curl -fsSL {RAW}/{tag}/scripts/bootstrap.sh | WHISPY_REF={tag} bash",
        tag = version.tag()
    )
}

/// How a check ended.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Checked {
    /// The last published version (it may be this one, or older).
    Latest(Version),
    Failed(String),
}

/// How an install ended, when this process is still there to see it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Installed {
    /// The script succeeded without restarting this process (a script that
    /// found nothing to rebuild, no systemd user session, or a reinstall that
    /// missed the running app, as the 2.5.0 one did on macOS).
    Done,
    /// The script stopped before sudo: run [`terminal_command`] by hand.
    NeedsTerminal,
    /// The reason, shown on the row.
    Failed(String),
}

/// The update row, as every menu shows it: always there, a grey status line
/// at rest. Choosing it, when `enabled`, installs the version it names.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Row {
    pub title: String,
    /// `false`: shown grey and cannot be chosen (the status line at rest, or
    /// an install running).
    pub enabled: bool,
    /// The title changes on its own soon (an install is running): the Omarchy
    /// panel asks again until it settles.
    pub transient: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Phase {
    /// Not known yet (no answer, or offline): « Whispy 2.6.0 ».
    Unknown,
    /// A check found nothing newer: « Whispy 2.6.0 · up to date ».
    UpToDate,
    Available(Version),
    Installing(Version),
    /// The reason, shown on the row.
    Failed(Version, String),
    /// Installed, but this old process still runs.
    NotRestarted(Version),
    NeedsTerminal(Version),
}

impl Phase {
    fn row(&self, current: Version) -> Row {
        let (title, enabled, transient) = match self {
            Phase::Unknown => (texts::current(current), false, false),
            Phase::UpToDate => (texts::up_to_date(current), false, false),
            Phase::Available(version) => (texts::available(*version), true, false),
            Phase::Installing(version) => (texts::updating_to(*version), false, true),
            Phase::Failed(version, reason) => (texts::update_failed(*version, reason), true, false),
            Phase::NotRestarted(version) => (texts::not_restarted(*version), false, false),
            Phase::NeedsTerminal(version) => (
                texts::needs_terminal(&terminal_command(*version)),
                true,
                false,
            ),
        };
        Row {
            title,
            enabled,
            transient,
        }
    }

    /// The version an install would get.
    fn installable(&self) -> Option<Version> {
        match self {
            Phase::Available(version)
            | Phase::Failed(version, _)
            | Phase::NeedsTerminal(version) => Some(*version),
            Phase::Unknown | Phase::UpToDate | Phase::Installing(_) | Phase::NotRestarted(_) => {
                None
            }
        }
    }
}

type CheckFn = dyn Fn() -> Checked + Send + Sync;
type InstallFn = dyn Fn(Version) -> Installed + Send + Sync;
type ChangedFn = dyn Fn(&Row) + Send + Sync;

struct Shared {
    phase: Phase,
    checking: bool,
    last_check: Option<SystemTime>,
    on_change: Option<Arc<ChangedFn>>,
}

/// The update state, shared by the menus, the control socket and the daily
/// clock. Cheap to clone. Checks and installs run on their own threads, so a
/// slow or absent network never holds a menu or a dictation.
#[derive(Clone)]
pub struct Updater {
    shared: Arc<Mutex<Shared>>,
    current: Version,
    check: Arc<CheckFn>,
    install: Arc<InstallFn>,
}

impl Updater {
    /// The real one: `git ls-remote` and the tag's `bootstrap.sh`.
    pub fn new() -> Updater {
        Updater::with(
            Version::current(),
            || check_remote(REPOSITORY),
            install_release,
        )
    }

    /// With a fake check and install, for tests.
    pub fn with(
        current: Version,
        check: impl Fn() -> Checked + Send + Sync + 'static,
        install: impl Fn(Version) -> Installed + Send + Sync + 'static,
    ) -> Updater {
        Updater {
            shared: Arc::new(Mutex::new(Shared {
                phase: Phase::Unknown,
                checking: false,
                last_check: None,
                on_change: None,
            })),
            current,
            check: Arc::new(check),
            install: Arc::new(install),
        }
    }

    /// Called with the new row on every change, from any thread.
    pub fn set_on_change(&self, on_change: impl Fn(&Row) + Send + Sync + 'static) {
        self.lock().on_change = Some(Arc::new(on_change));
    }

    /// The row to show.
    pub fn row(&self) -> Row {
        self.lock().phase.row(self.current)
    }

    /// Starts a check, unless one or an install is running. The row changes
    /// only once it answers (a failure changes nothing).
    pub fn check(&self) {
        {
            let mut shared = self.lock();
            if shared.checking || matches!(shared.phase, Phase::Installing(_)) {
                return;
            }
            shared.checking = true;
            shared.last_check = Some(SystemTime::now());
        }
        let updater = self.clone();
        let spawned = thread::Builder::new()
            .name("whispy2-update-check".into())
            .spawn(move || {
                let checked = (updater.check)();
                updater.checked(checked);
            });
        if let Err(error) = spawned {
            self.checked(Checked::Failed(error.to_string()));
        }
    }

    fn checked(&self, checked: Checked) {
        let changed = {
            let mut shared = self.lock();
            shared.checking = false;
            if matches!(shared.phase, Phase::Installing(_)) {
                return;
            }
            let phase = match checked {
                Checked::Latest(latest) if latest > self.current => {
                    log::line(&format!(
                        "update: {latest} is published (this is {})",
                        self.current
                    ));
                    match shared.phase {
                        // The same version, already tried: keep what it said.
                        Phase::Failed(v, _) | Phase::NeedsTerminal(v) | Phase::NotRestarted(v)
                            if v == latest =>
                        {
                            shared.phase.clone()
                        }
                        _ => Phase::Available(latest),
                    }
                }
                Checked::Latest(latest) => {
                    log::line(&format!(
                        "update: up to date ({}, last published {latest})",
                        self.current
                    ));
                    Phase::UpToDate
                }
                Checked::Failed(reason) => {
                    // Silent: an update offered before stays offered.
                    log::line(&format!("update: cannot check for updates ({reason})"));
                    shared.phase.clone()
                }
            };
            let changed = shared.phase != phase;
            shared.phase = phase;
            changed
        };
        if changed {
            self.changed();
        }
    }

    /// Starts installing the offered version. `false` when none is offered.
    pub fn install(&self) -> bool {
        let version = {
            let mut shared = self.lock();
            let Some(version) = shared.phase.installable() else {
                return false;
            };
            shared.phase = Phase::Installing(version);
            version
        };
        log::line(&format!(
            "update: installing {version} (log: ~/.whispy/v2/update.log)"
        ));
        self.changed();
        let updater = self.clone();
        let spawned = thread::Builder::new()
            .name("whispy2-update-install".into())
            .spawn(move || {
                let installed = (updater.install)(version);
                updater.installed(version, installed);
            });
        if let Err(error) = spawned {
            self.installed(version, Installed::Failed(error.to_string()));
        }
        true
    }

    fn installed(&self, version: Version, installed: Installed) {
        let phase = match installed {
            Installed::Done => {
                log::line(&format!(
                    "update: the {version} install ended without a restart"
                ));
                Phase::NotRestarted(version)
            }
            Installed::NeedsTerminal => {
                log::line(&format!(
                    "update: {version} needs sudo; run in a terminal: {}",
                    terminal_command(version)
                ));
                Phase::NeedsTerminal(version)
            }
            Installed::Failed(reason) => {
                log::line(&format!("update: installing {version} failed ({reason})"));
                Phase::Failed(version, reason)
            }
        };
        self.lock().phase = phase;
        self.changed();
    }

    /// The automatic checks: now, then once a day (by the wall clock).
    pub fn start_daily(&self) {
        let updater = self.clone();
        let spawned = thread::Builder::new()
            .name("whispy2-update-daily".into())
            .spawn(move || loop {
                let last = updater.lock().last_check;
                if is_due(last, SystemTime::now()) {
                    updater.check();
                }
                thread::sleep(DAILY_POLL);
            });
        if let Err(error) = spawned {
            log::line(&format!("update: the daily check could not start: {error}"));
        }
    }

    fn changed(&self) {
        let (row, on_change) = {
            let shared = self.lock();
            (shared.phase.row(self.current), shared.on_change.clone())
        };
        if let Some(on_change) = on_change {
            on_change(&row);
        }
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Shared> {
        self.shared
            .lock()
            .unwrap_or_else(|poison| poison.into_inner())
    }
}

impl Default for Updater {
    fn default() -> Self {
        Updater::new()
    }
}

/// Whether an automatic check is due: never checked, a day gone, or a clock
/// set back.
fn is_due(last: Option<SystemTime>, now: SystemTime) -> bool {
    match last {
        None => true,
        Some(last) => now
            .duration_since(last)
            .map_or(true, |since| since >= DAILY),
    }
}

/// The `update` part of the control socket's `status` reply.
/// `action` is the socket request a click sends: `update`, or `null` while
/// an install runs.
pub fn row_json(row: &Row) -> String {
    let action = if row.enabled { "\"update\"" } else { "null" };
    format!(
        "{{\"title\":{},\"action\":{action},\"transient\":{}}}",
        crate::journal::json_string(&row.title),
        row.transient
    )
}

// ---- The real check and install ------------------------------------------

/// `git ls-remote --tags --refs <repository>`, killed after [`CHECK_TIMEOUT`].
fn check_remote(repository: &str) -> Checked {
    let child = Command::new("git")
        .args(["ls-remote", "--tags", "--refs", repository])
        // Never a credential prompt: a public repository needs none.
        .env("GIT_TERMINAL_PROMPT", "0")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();
    let mut child = match child {
        Ok(child) => child,
        Err(error) => return Checked::Failed(format!("git: {error}")),
    };
    let deadline = Instant::now() + CHECK_TIMEOUT;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return Checked::Failed(format!("git ls-remote took over {CHECK_TIMEOUT:?}"));
            }
            Ok(None) => thread::sleep(Duration::from_millis(100)),
            Err(error) => return Checked::Failed(error.to_string()),
        }
    }
    let output = match child.wait_with_output() {
        Ok(output) => output,
        Err(error) => return Checked::Failed(error.to_string()),
    };
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Checked::Failed(
            stderr
                .trim()
                .lines()
                .last()
                .unwrap_or("git failed")
                .to_string(),
        );
    }
    match latest_tag(&String::from_utf8_lossy(&output.stdout)) {
        Some(latest) => Checked::Latest(latest),
        None => Checked::Failed("no vX.Y.Z tag published".to_string()),
    }
}

/// Why the last install in `update.log` failed: its last `[FAIL]` line (or
/// curl's), colours stripped and kept short for a menu row.
pub fn failure_reason(log_text: &str) -> Option<String> {
    let run = log_text
        .rsplit_once("=== Whispy update to ")
        .map_or(log_text, |(_, run)| run);
    let line = run
        .lines()
        .map(strip_colours)
        .map(|line| line.trim().to_string())
        .rfind(|line| line.starts_with("[FAIL]") || line.starts_with("could not download"))?;
    let reason = line.trim_start_matches("[FAIL]").trim();
    const MAX: usize = 80;
    Some(if reason.chars().count() > MAX {
        let short: String = reason.chars().take(MAX - 1).collect();
        format!("{}\u{2026}", short.trim_end())
    } else {
        reason.to_string()
    })
}

/// `text` without its ANSI colour sequences (`ESC [ … m`).
fn strip_colours(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars();
    while let Some(c) = chars.next() {
        if c == '\u{1b}' {
            for c in chars.by_ref() {
                if c.is_ascii_alphabetic() {
                    break;
                }
            }
        } else {
            out.push(c);
        }
    }
    out
}

/// The script that downloads a tag's `bootstrap.sh` and runs it unattended,
/// its output appended to the log. Positional parameters: the tag, the raw
/// URL base, the log path. Never interpolated into the script text.
pub const INSTALL_SCRIPT: &str = r#"set -u
tag="$1"; raw="$2"; log="$3"
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
mkdir -p "$(dirname "$log")"
echo "=== Whispy update to $tag, $(date) ===" >>"$log"
script="$(mktemp)" || exit 1
if ! curl -fsSL "$raw/$tag/scripts/bootstrap.sh" -o "$script" >>"$log" 2>&1; then
    rm -f "$script"; echo "could not download bootstrap.sh for $tag" >>"$log"; exit 1
fi
WHISPY_REF="$tag" WHISPY_UNATTENDED=1 bash "$script" </dev/null >>"$log" 2>&1
code=$?
rm -f "$script"
echo "=== exit $code ===" >>"$log"
exit "$code"
"#;

/// The arguments of `/bin/sh` that install `version`.
pub fn install_arguments(version: Version, log_path: &Path) -> Vec<String> {
    vec![
        "-c".to_string(),
        INSTALL_SCRIPT.to_string(),
        "whispy2-update".to_string(),
        version.tag(),
        RAW.to_string(),
        log_path.display().to_string(),
    ]
}

/// What runs the install script: directly (macOS, or Linux without a
/// systemd user session), or as a transient `systemd --user` unit that
/// `--wait`s, so the exit code still comes back when the app survives.
pub fn launcher(use_systemd_run: bool, environment: &[(String, String)]) -> Vec<String> {
    if !use_systemd_run {
        return vec!["/bin/sh".to_string()];
    }
    let mut command = vec![
        "systemd-run".to_string(),
        "--user".to_string(),
        "--quiet".to_string(),
        "--collect".to_string(),
        "--wait".to_string(),
        format!("--unit={LINUX_UNIT}"),
    ];
    for (name, value) in environment {
        command.push(format!("--setenv={name}={value}"));
    }
    command.push("/bin/sh".to_string());
    command
}

fn update_log() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_default()
        .join(".whispy/v2/update.log")
}

fn has_user_systemd() -> bool {
    cfg!(target_os = "linux")
        && Command::new("systemctl")
            .args(["--user", "show-environment"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
}

/// Runs the tag's `bootstrap.sh` and waits for it. On success the script
/// restarts Whispy, usually before this returns.
fn install_release(version: Version) -> Installed {
    let use_systemd_run = has_user_systemd();
    // A transient unit starts with the user manager's environment: hand it
    // what the script reads (the session kind picks the clipboard package).
    let environment: Vec<(String, String)> = [
        "PATH",
        "DISPLAY",
        "XAUTHORITY",
        "WAYLAND_DISPLAY",
        "XDG_SESSION_TYPE",
    ]
    .iter()
    .filter_map(|name| {
        std::env::var(name)
            .ok()
            .filter(|value| !value.is_empty())
            .map(|value| (name.to_string(), value))
    })
    .collect();
    let mut command = launcher(use_systemd_run, &environment);
    let program = command.remove(0);
    let mut process = Command::new(program);
    process
        .args(command)
        .args(install_arguments(version, &update_log()))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    // Its own process group: the reinstall quits this app, not the script.
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        process.process_group(0);
    }
    match process.status() {
        Ok(status) if status.success() => Installed::Done,
        Ok(status) if status.code() == Some(NEEDS_TERMINAL_EXIT) => Installed::NeedsTerminal,
        Ok(status) => Installed::Failed(
            std::fs::read_to_string(update_log())
                .ok()
                .and_then(|text| failure_reason(&text))
                .unwrap_or_else(|| format!("bootstrap.sh exited with {status}")),
        ),
        Err(error) => Installed::Failed(error.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    const CURRENT: Version = Version(2, 4, 0);

    fn wait_for(updater: &Updater, settled: impl Fn(&Row) -> bool) -> Row {
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            let row = updater.row();
            if settled(&row) {
                return row;
            }
            assert!(Instant::now() < deadline, "row never settled: {row:?}");
            thread::sleep(Duration::from_millis(5));
        }
    }

    /// Waits until the check in flight has ended.
    fn wait_checked(updater: &Updater) {
        let deadline = Instant::now() + Duration::from_secs(5);
        while updater.lock().checking {
            assert!(Instant::now() < deadline, "the check never ended");
            thread::sleep(Duration::from_millis(5));
        }
    }

    fn offered(row: &Row) -> bool {
        row.enabled
    }

    /// The grey version line: shown, but it cannot be chosen.
    fn grey(title: &str) -> Row {
        Row {
            title: title.into(),
            enabled: false,
            transient: false,
        }
    }

    fn updater(checked: Checked, installed: Installed) -> Updater {
        Updater::with(CURRENT, move || checked.clone(), move |_| installed.clone())
    }

    #[test]
    fn versions_parse_from_the_crate_and_from_tags() {
        assert_eq!(Version::parse("2.4.0"), Some(Version(2, 4, 0)));
        assert_eq!(Version::parse("v10.0.12"), Some(Version(10, 0, 12)));
        for bad in ["v2.4", "2.4.0.1", "v2.4.0-rc1", "", "v", "va.b.c", "2..0"] {
            assert_eq!(Version::parse(bad), None, "{bad:?}");
        }
        assert!(Version(2, 10, 0) > Version(2, 9, 9));
        assert_eq!(Version(2, 5, 0).tag(), "v2.5.0");
        assert_eq!(Version::current().to_string(), env!("CARGO_PKG_VERSION"));
    }

    #[test]
    fn the_latest_tag_is_the_highest_version_not_the_last_line() {
        let output = "\
5e831c1c\trefs/tags/v2.10.0
b91d9ff3\trefs/tags/v2.9.0
7c70c177\trefs/tags/v2.10.0^{}
1111111\trefs/tags/v1
2222222\trefs/tags/nightly
3333333\trefs/tags/v3.0.0-rc1
";
        assert_eq!(latest_tag(output), Some(Version(2, 10, 0)));
        assert_eq!(latest_tag(""), None);
        assert_eq!(latest_tag("abc\trefs/heads/main\n"), None);
    }

    #[test]
    fn before_any_answer_the_row_is_the_grey_version_line() {
        let updater = updater(Checked::Latest(CURRENT), Installed::Done);
        assert_eq!(updater.row(), grey("Whispy 2.4.0"));
        assert!(!updater.install(), "the version line installs nothing");
    }

    #[test]
    fn up_to_date_the_row_says_so_in_grey_and_cannot_be_chosen() {
        let updater = updater(Checked::Latest(CURRENT), Installed::Done);
        let (seen, rows) = mpsc::channel();
        updater.set_on_change(move |row| {
            let _ = seen.send(row.clone());
        });
        updater.check();
        wait_checked(&updater);
        let line = grey("Whispy 2.4.0 \u{b7} up to date");
        assert_eq!(updater.row(), line);
        assert_eq!(
            rows.try_iter().collect::<Vec<_>>(),
            std::slice::from_ref(&line)
        );
        assert!(!updater.install(), "the version line installs nothing");
        // An older published version (a tag removed) changes nothing.
        let ahead = Updater::with(
            CURRENT,
            || Checked::Latest(Version(2, 3, 9)),
            |_| Installed::Done,
        );
        ahead.check();
        wait_checked(&ahead);
        assert_eq!(ahead.row(), line);
    }

    #[test]
    fn up_to_date_in_french_the_row_says_a_jour() {
        crate::i18n::set(crate::i18n::Lang::Fr);
        assert_eq!(
            Phase::UpToDate.row(Version(2, 6, 0)).title,
            "Whispy 2.6.0 \u{b7} \u{e0} jour"
        );
    }

    #[test]
    fn criterion_1_a_newer_release_shows_update_available_and_installs_nothing() {
        let (asked, installs) = mpsc::channel();
        let updater = Updater::with(
            CURRENT,
            || Checked::Latest(Version(2, 5, 0)),
            move |version| {
                let _ = asked.send(version);
                Installed::Done
            },
        );
        updater.check();
        let row = wait_for(&updater, offered);
        assert_eq!(row.title, "Update available (2.5.0)");
        assert!(!row.transient);
        // Another check finds the same offer: still offered, still nothing run.
        updater.check();
        wait_checked(&updater);
        assert_eq!(updater.row(), row);
        assert!(installs.try_recv().is_err(), "finding it installs nothing");
    }

    #[test]
    fn criterion_5_a_failed_check_adds_nothing_and_keeps_an_offered_update() {
        let fail = Arc::new(Mutex::new(true));
        let failing = Arc::clone(&fail);
        let updater = Updater::with(
            CURRENT,
            move || {
                if *failing.lock().unwrap() {
                    Checked::Failed("offline".into())
                } else {
                    Checked::Latest(Version(2, 5, 0))
                }
            },
            |_| Installed::Done,
        );
        updater.check();
        wait_checked(&updater);
        assert_eq!(updater.row(), grey("Whispy 2.4.0"), "offline: nothing said");

        *fail.lock().unwrap() = false;
        updater.check();
        wait_for(&updater, offered);
        *fail.lock().unwrap() = true;
        updater.check();
        wait_checked(&updater);
        assert_eq!(updater.row().title, "Update available (2.5.0)");
    }

    #[test]
    fn criterion_3_choosing_the_offer_installs_it_and_shows_it_running() {
        let (release, installing) = mpsc::channel::<()>();
        let release = Mutex::new(Some(release));
        let (asked, versions) = mpsc::channel();
        let gate = Mutex::new(installing);
        let updater = Updater::with(
            CURRENT,
            || Checked::Latest(Version(2, 5, 0)),
            move |version| {
                asked.send(version).unwrap();
                let _ = gate.lock().unwrap().recv();
                Installed::Done
            },
        );
        assert!(!updater.install(), "nothing is offered yet");
        updater.check();
        wait_for(&updater, offered);
        assert!(updater.install());
        assert_eq!(
            versions.recv_timeout(Duration::from_secs(5)).unwrap(),
            Version(2, 5, 0)
        );
        let row = updater.row();
        assert_eq!(row.title, "Updating to 2.5.0\u{2026}");
        assert!(!row.enabled && row.transient);
        // A check while installing changes nothing.
        updater.check();
        assert_eq!(updater.row().title, "Updating to 2.5.0\u{2026}");
        drop(release.lock().unwrap().take());
        // The script ended but this process still runs (the 2.5.0 macOS
        // update, #50): the row says so instead of vanishing.
        let row = wait_for(&updater, |row| !row.transient);
        assert_eq!(
            row.title,
            "2.5.0 is installed \u{2014} quit and reopen Whispy to finish"
        );
        assert!(!row.enabled, "nothing to install again");
        // The daily check keeps it shown.
        updater.check();
        wait_checked(&updater);
        assert_eq!(updater.row(), row);
    }

    #[test]
    fn criterion_4_an_install_that_needs_sudo_shows_the_command_to_run() {
        let updater = updater(Checked::Latest(Version(2, 5, 0)), Installed::NeedsTerminal);
        updater.check();
        wait_for(&updater, offered);
        updater.install();
        let row = wait_for(&updater, |row| !row.transient);
        assert_eq!(
            row.title,
            "Update needs your password \u{2014} run in a terminal: curl -fsSL https://raw.githubusercontent.com/albrones/whispy/v2.5.0/scripts/bootstrap.sh | WHISPY_REF=v2.5.0 bash"
        );
        // The daily check keeps the command shown for the same version.
        updater.check();
        wait_checked(&updater);
        assert_eq!(updater.row(), row);
    }

    #[test]
    fn a_failed_install_can_be_tried_again() {
        let updater = updater(
            Checked::Latest(Version(2, 5, 0)),
            Installed::Failed("Build failed".into()),
        );
        updater.check();
        wait_for(&updater, offered);
        updater.install();
        let row = wait_for(&updater, |row| !row.transient);
        assert_eq!(
            row.title,
            "Update to 2.5.0 failed: Build failed \u{2014} try again"
        );
        assert!(row.enabled);
    }

    #[test]
    fn the_failure_reason_is_the_last_fail_line_of_the_last_run() {
        let log = "\
=== Whispy update to v2.5.0, Fri ===
\u{1b}[0;31m[FAIL] old run\u{1b}[0m
=== exit 1 ===
=== Whispy update to v2.5.1, Fri ===
   Compiling whispy2 v2.5.1
\u{1b}[0;31m[FAIL] Build failed \u{2014} /Applications/Whispy V2.app left untouched.\u{1b}[0m
=== exit 1 ===
";
        assert_eq!(
            failure_reason(log).as_deref(),
            Some("Build failed \u{2014} /Applications/Whispy V2.app left untouched.")
        );
        assert_eq!(
            failure_reason(
                "=== Whispy update to v2.5.1 ===\ncould not download bootstrap.sh for v2.5.1\n"
            )
            .as_deref(),
            Some("could not download bootstrap.sh for v2.5.1")
        );
        assert_eq!(
            failure_reason("=== Whispy update to v2.5.1 ===\n=== exit 2 ===\n"),
            None
        );
        let long = format!("[FAIL] {}", "x".repeat(200));
        assert_eq!(failure_reason(&long).unwrap().chars().count(), 80);
    }

    #[test]
    fn a_check_is_due_once_a_day_or_after_the_clock_went_back() {
        let now = SystemTime::now();
        assert!(is_due(None, now));
        assert!(!is_due(Some(now - Duration::from_secs(3600)), now));
        assert!(is_due(Some(now - DAILY), now));
        assert!(is_due(Some(now + Duration::from_secs(60)), now));
    }

    #[test]
    fn the_status_json_names_the_socket_request_of_the_row() {
        let row = Row {
            title: "Update available (2.5.0)".into(),
            enabled: true,
            transient: false,
        };
        assert_eq!(
            row_json(&row),
            "{\"title\":\"Update available (2.5.0)\",\"action\":\"update\",\"transient\":false}"
        );
        let busy = Row {
            title: texts::updating_to(Version(2, 5, 0)),
            enabled: false,
            transient: true,
        };
        assert!(row_json(&busy).contains("\"action\":null,\"transient\":true"));
    }

    #[test]
    fn the_linux_install_runs_outside_the_service_and_waits() {
        let env = [("XDG_SESSION_TYPE".to_string(), "wayland".to_string())];
        let command = launcher(true, &env);
        assert_eq!(command[0], "systemd-run");
        assert!(command.contains(&"--user".to_string()));
        assert!(command.contains(&"--wait".to_string()));
        assert!(command.contains(&"--collect".to_string()));
        assert!(command.contains(&"--setenv=XDG_SESSION_TYPE=wayland".to_string()));
        assert_eq!(command.last().unwrap(), "/bin/sh");
        assert_eq!(launcher(false, &env), ["/bin/sh"]);
    }

    #[test]
    fn the_install_script_runs_the_tags_bootstrap_unattended() {
        let args = install_arguments(Version(2, 5, 0), Path::new("/tmp/a b/update.log"));
        assert_eq!(args[0], "-c");
        assert_eq!(&args[3..], ["v2.5.0", RAW, "/tmp/a b/update.log"]);
        let script = &args[1];
        assert!(script.contains("WHISPY_REF=\"$tag\" WHISPY_UNATTENDED=1 bash \"$script\""));
        assert!(script.contains("\"$raw/$tag/scripts/bootstrap.sh\""));
        assert!(
            !script.contains("v2.5.0"),
            "values are parameters, not script text"
        );
    }

    #[test]
    fn the_install_script_reports_the_bootstrap_exit_code() {
        // A fake « raw » server: a file:// tree that curl reads like the real one.
        let root = std::env::temp_dir().join(format!("whispy2-update-{}", std::process::id()));
        let scripts = root.join("v2.5.0/scripts");
        std::fs::create_dir_all(&scripts).unwrap();
        std::fs::write(
            scripts.join("bootstrap.sh"),
            "[ \"$WHISPY_REF\" = v2.5.0 ] && [ \"$WHISPY_UNATTENDED\" = 1 ] && echo ran && exit 3\nexit 9\n",
        )
        .unwrap();
        let log_path = root.join("logs/update.log");
        let mut args = install_arguments(Version(2, 5, 0), &log_path);
        args[4] = format!("file://{}", root.display());
        let status = Command::new("/bin/sh").args(&args).status().unwrap();
        assert_eq!(status.code(), Some(NEEDS_TERMINAL_EXIT));
        let log_text = std::fs::read_to_string(&log_path).unwrap();
        assert!(
            log_text.contains("ran") && log_text.contains("=== exit 3 ==="),
            "{log_text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

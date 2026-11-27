//! Updating Whispy from its menu: the macOS menu bar, the Linux tray icon and
//! the Omarchy bar panel (through the control socket).
//!
//! - **Check**: the last published version is the highest `vX.Y.Z` tag of the
//!   public repository, read with `git ls-remote --tags` (no API, no token).
//!   Whispy checks at startup, then once a day, and whenever « Check for
//!   Updates » is chosen. Only a check asked for by hand says how it went (the
//!   row's title changes for a few seconds); an automatic one that fails is
//!   only logged.
//! - **Install**: « Update to X.Y.Z » runs that tag's `scripts/bootstrap.sh`
//!   with `WHISPY_REF=vX.Y.Z`, detached from the app: the script rebuilds,
//!   replaces and restarts Whispy, so this process does not live to see it
//!   succeed. Under Linux it runs as a transient `systemd --user` unit: the
//!   restart of `whispy2.service` stops every process of the unit's cgroup,
//!   the script included otherwise. `WHISPY_UNATTENDED=1` makes the script
//!   stop with [`NEEDS_TERMINAL_EXIT`] rather than ask for a password (sudo),
//!   and the row then shows the command to run in a terminal.
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

/// Every text the update shows, in one place, to be translated later (#64).
pub mod texts {
    use super::Version;

    pub const CHECK: &str = "Check for Updates";
    pub const CHECKING: &str = "Checking for Updates\u{2026}";
    pub const UP_TO_DATE: &str = "Whispy is up to date";
    pub const CANNOT_CHECK: &str = "Can't check for updates";

    pub fn update_to(version: Version) -> String {
        format!("Update to {version}")
    }

    pub fn updating_to(version: Version) -> String {
        format!("Updating to {version}\u{2026}")
    }

    pub fn update_failed(version: Version) -> String {
        format!("Update to {version} failed \u{2014} try again (see ~/.whispy/v2/update.log)")
    }

    pub fn needs_terminal(command: &str) -> String {
        format!("Update needs your password \u{2014} run in a terminal: {command}")
    }
}

/// The public repository the versions are read from.
pub const REPOSITORY: &str = "https://github.com/albrones/whispy.git";
/// Where a tag's files are served raw.
const RAW: &str = "https://raw.githubusercontent.com/albrones/whispy";
/// The exit code of `bootstrap.sh` under `WHISPY_UNATTENDED=1` when a step
/// would need sudo (or a dialog): nothing was changed.
pub const NEEDS_TERMINAL_EXIT: i32 = 3;
/// How long a hand-made check shows its result.
pub const FLASH: Duration = Duration::from_secs(5);
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
    /// found nothing to rebuild, or no systemd user session).
    Done,
    /// The script stopped before sudo: run [`terminal_command`] by hand.
    NeedsTerminal,
    Failed(String),
}

/// What a row does when chosen.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Check,
    Install,
}

/// The update row, as every menu shows it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Row {
    pub title: String,
    /// `None`: shown disabled (a check or an install is running).
    pub action: Option<Action>,
    /// The title changes on its own soon (a check, an install, a result
    /// shown for a few seconds): the Omarchy panel asks again until it settles.
    pub transient: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Phase {
    Idle,
    Checking {
        manual: bool,
    },
    Available(Version),
    Installing(Version),
    /// A hand-made check's result, shown until `until`.
    Flash {
        text: &'static str,
        until: Instant,
    },
    Failed(Version),
    NeedsTerminal(Version),
}

impl Phase {
    fn row(&self) -> Row {
        let (title, action, transient) = match self {
            Phase::Idle => (texts::CHECK.to_string(), Some(Action::Check), false),
            Phase::Checking { .. } => (texts::CHECKING.to_string(), None, true),
            Phase::Available(version) => (texts::update_to(*version), Some(Action::Install), false),
            Phase::Installing(version) => (texts::updating_to(*version), None, true),
            Phase::Flash { text, .. } => (text.to_string(), Some(Action::Check), true),
            Phase::Failed(version) => {
                (texts::update_failed(*version), Some(Action::Install), false)
            }
            Phase::NeedsTerminal(version) => (
                texts::needs_terminal(&terminal_command(*version)),
                Some(Action::Check),
                false,
            ),
        };
        Row {
            title,
            action,
            transient,
        }
    }

    /// The version an install would get.
    fn installable(&self) -> Option<Version> {
        match self {
            Phase::Available(version) | Phase::Failed(version) => Some(*version),
            _ => None,
        }
    }
}

type CheckFn = dyn Fn() -> Checked + Send + Sync;
type InstallFn = dyn Fn(Version) -> Installed + Send + Sync;
type ChangedFn = dyn Fn(&Row) + Send + Sync;

struct Shared {
    phase: Phase,
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
    flash: Duration,
}

impl Updater {
    /// The real one: `git ls-remote` and the tag's `bootstrap.sh`.
    pub fn new() -> Updater {
        Updater::with(
            Version::current(),
            || check_remote(REPOSITORY),
            install_release,
            FLASH,
        )
    }

    /// With a fake check and install, for tests.
    pub fn with(
        current: Version,
        check: impl Fn() -> Checked + Send + Sync + 'static,
        install: impl Fn(Version) -> Installed + Send + Sync + 'static,
        flash: Duration,
    ) -> Updater {
        Updater {
            shared: Arc::new(Mutex::new(Shared {
                phase: Phase::Idle,
                last_check: None,
                on_change: None,
            })),
            current,
            check: Arc::new(check),
            install: Arc::new(install),
            flash,
        }
    }

    /// Called with the new row on every change, from any thread.
    pub fn set_on_change(&self, on_change: impl Fn(&Row) + Send + Sync + 'static) {
        self.lock().on_change = Some(Arc::new(on_change));
    }

    pub fn row(&self) -> Row {
        self.lock().phase.row()
    }

    /// What the row's choice does: check, or install the version it names.
    pub fn choose(&self, action: Action) {
        match action {
            Action::Check => self.check(true),
            Action::Install => {
                self.install();
            }
        }
    }

    /// Starts a check, unless one or an install is running. `manual` checks
    /// show their result; automatic ones fail silently.
    pub fn check(&self, manual: bool) {
        {
            let mut shared = self.lock();
            if matches!(shared.phase, Phase::Checking { .. } | Phase::Installing(_)) {
                return;
            }
            // An automatic check keeps an offered update offered while it runs.
            if manual || !matches!(shared.phase, Phase::Available(_)) {
                shared.phase = Phase::Checking { manual };
            }
            shared.last_check = Some(SystemTime::now());
        }
        self.changed();
        let updater = self.clone();
        let spawned = thread::Builder::new()
            .name("whispy2-update-check".into())
            .spawn(move || {
                let checked = (updater.check)();
                updater.checked(manual, checked);
            });
        if let Err(error) = spawned {
            self.checked(manual, Checked::Failed(error.to_string()));
        }
    }

    fn checked(&self, manual: bool, checked: Checked) {
        let flash_until = Instant::now() + self.flash;
        let phase = match &checked {
            Checked::Latest(latest) if *latest > self.current => {
                log::line(&format!(
                    "update: {latest} is published (this is {})",
                    self.current
                ));
                Phase::Available(*latest)
            }
            Checked::Latest(latest) => {
                log::line(&format!(
                    "update: up to date ({}, last published {latest})",
                    self.current
                ));
                if manual {
                    Phase::Flash {
                        text: texts::UP_TO_DATE,
                        until: flash_until,
                    }
                } else {
                    Phase::Idle
                }
            }
            Checked::Failed(reason) => {
                log::line(&format!("update: cannot check for updates ({reason})"));
                if manual {
                    Phase::Flash {
                        text: texts::CANNOT_CHECK,
                        until: flash_until,
                    }
                } else {
                    // Silent: an update offered before stays offered.
                    let shared = self.lock();
                    match shared.phase {
                        Phase::Available(version) => Phase::Available(version),
                        _ => Phase::Idle,
                    }
                }
            }
        };
        let is_flash = matches!(phase, Phase::Flash { .. });
        self.lock().phase = phase;
        self.changed();
        if is_flash {
            self.end_flash_later(flash_until);
        }
    }

    /// Puts the row back to « Check for Updates » once the result has been seen.
    fn end_flash_later(&self, until: Instant) {
        let updater = self.clone();
        let _ = thread::Builder::new()
            .name("whispy2-update-flash".into())
            .spawn(move || {
                thread::sleep(until.saturating_duration_since(Instant::now()));
                let ended = {
                    let mut shared = updater.lock();
                    let is_same =
                        matches!(shared.phase, Phase::Flash { until: u, .. } if u == until);
                    if is_same {
                        shared.phase = Phase::Idle;
                    }
                    is_same
                };
                if ended {
                    updater.changed();
                }
            });
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
                Phase::Idle
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
                Phase::Failed(version)
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
                    updater.check(false);
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
            (shared.phase.row(), shared.on_change.clone())
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
pub fn row_json(row: &Row) -> String {
    let action = match row.action {
        Some(Action::Check) => "\"check-update\"",
        Some(Action::Install) => "\"update\"",
        None => "null",
    };
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
        Ok(status) => Installed::Failed(format!("bootstrap.sh exited with {status}")),
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

    fn updater(checked: Checked, installed: Installed) -> Updater {
        Updater::with(
            CURRENT,
            move || checked.clone(),
            move |_| installed.clone(),
            Duration::from_millis(80),
        )
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
    fn at_rest_the_row_offers_a_check() {
        let row = updater(Checked::Latest(CURRENT), Installed::Done).row();
        assert_eq!(row.title, "Check for Updates");
        assert_eq!(row.action, Some(Action::Check));
        assert!(!row.transient);
    }

    #[test]
    fn criterion_1_a_newer_release_turns_the_row_into_update_to_it() {
        let updater = updater(Checked::Latest(Version(2, 5, 0)), Installed::Done);
        updater.check(false);
        let row = wait_for(&updater, |row| row.action == Some(Action::Install));
        assert_eq!(row.title, "Update to 2.5.0");
        assert!(!row.transient);
    }

    #[test]
    fn criterion_2_a_manual_check_says_up_to_date_for_a_few_seconds() {
        let updater = updater(Checked::Latest(CURRENT), Installed::Done);
        updater.check(true);
        let row = wait_for(&updater, |row| row.title != texts::CHECKING);
        assert_eq!(row.title, "Whispy is up to date");
        assert!(row.transient);
        let row = wait_for(&updater, |row| !row.transient);
        assert_eq!(row.title, "Check for Updates");
    }

    #[test]
    fn criterion_5_a_failed_manual_check_says_so_and_an_automatic_one_stays_silent() {
        let updater = updater(Checked::Failed("offline".into()), Installed::Done);
        let (seen, titles) = mpsc::channel();
        updater.set_on_change(move |row| {
            let _ = seen.send(row.title.clone());
        });
        updater.check(false);
        wait_for(&updater, |row| !row.transient);
        let automatic: Vec<String> = titles.try_iter().collect();
        assert!(
            !automatic.iter().any(|t| t == texts::CANNOT_CHECK),
            "{automatic:?}"
        );
        assert_eq!(updater.row().title, "Check for Updates");

        updater.check(true);
        let row = wait_for(&updater, |row| row.title != texts::CHECKING);
        assert_eq!(row.title, "Can't check for updates");
        assert_eq!(
            wait_for(&updater, |row| !row.transient).title,
            "Check for Updates"
        );
    }

    #[test]
    fn a_failed_automatic_check_keeps_an_offered_update() {
        let fail = Arc::new(Mutex::new(false));
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
            Duration::from_millis(50),
        );
        updater.check(false);
        wait_for(&updater, |row| row.action == Some(Action::Install));
        *fail.lock().unwrap() = true;
        updater.check(false);
        // Never shows « Checking » over the offer, and keeps it after the failure.
        thread::sleep(Duration::from_millis(50));
        assert_eq!(updater.row().title, "Update to 2.5.0");
    }

    #[test]
    fn criterion_3_install_runs_the_offered_version_and_shows_it_running() {
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
            Duration::from_millis(50),
        );
        assert!(!updater.install(), "nothing is offered yet");
        updater.check(false);
        wait_for(&updater, |row| row.action == Some(Action::Install));
        updater.choose(Action::Install);
        assert_eq!(
            versions.recv_timeout(Duration::from_secs(5)).unwrap(),
            Version(2, 5, 0)
        );
        let row = updater.row();
        assert_eq!(row.title, "Updating to 2.5.0\u{2026}");
        assert_eq!(row.action, None);
        // A check while installing changes nothing.
        updater.check(true);
        assert_eq!(updater.row().title, "Updating to 2.5.0\u{2026}");
        drop(release.lock().unwrap().take());
        // The script ended without restarting this process: back to rest.
        assert_eq!(
            wait_for(&updater, |row| !row.transient).title,
            "Check for Updates"
        );
    }

    #[test]
    fn criterion_4_an_install_that_needs_sudo_shows_the_command_to_run() {
        let updater = updater(Checked::Latest(Version(2, 5, 0)), Installed::NeedsTerminal);
        updater.check(false);
        wait_for(&updater, |row| row.action == Some(Action::Install));
        updater.install();
        let row = wait_for(&updater, |row| !row.transient);
        assert_eq!(
            row.title,
            "Update needs your password \u{2014} run in a terminal: curl -fsSL https://raw.githubusercontent.com/albrones/whispy/v2.5.0/scripts/bootstrap.sh | WHISPY_REF=v2.5.0 bash"
        );
        assert_eq!(row.action, Some(Action::Check));
    }

    #[test]
    fn a_failed_install_can_be_tried_again() {
        let updater = updater(
            Checked::Latest(Version(2, 5, 0)),
            Installed::Failed("exit 1".into()),
        );
        updater.check(false);
        wait_for(&updater, |row| row.action == Some(Action::Install));
        updater.install();
        let row = wait_for(&updater, |row| !row.transient);
        assert!(
            row.title.starts_with("Update to 2.5.0 failed"),
            "{}",
            row.title
        );
        assert_eq!(row.action, Some(Action::Install));
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
            title: "Update to 2.5.0".into(),
            action: Some(Action::Install),
            transient: false,
        };
        assert_eq!(
            row_json(&row),
            "{\"title\":\"Update to 2.5.0\",\"action\":\"update\",\"transient\":false}"
        );
        let busy = Row {
            title: texts::CHECKING.into(),
            action: None,
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

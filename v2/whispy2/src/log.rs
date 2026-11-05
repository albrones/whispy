//! V2's log: one file, rotated, mirrored to the terminal when there is one.
//!
//! Launched from Finder or at login, V2 has no terminal, so `eprintln!` went
//! nowhere (V1 got `~/.whispy.log` from its launcher; V2 needs its own). The
//! file is `~/.whispy/v2/whispy2.log`, mode 0600 in a 0700 directory, and
//! rolls over to `whispy2.log.1` (replacing the previous copy) when a line
//! would take it past [`LIMIT`]. Twenty lines of std instead of a logging
//! crate: V2 justifies every dependency, and this needs none.
//!
//! No line may contain dictated text: callers log sizes, durations and
//! outcomes, never the transcript.

use std::fs::{self, File, OpenOptions};
use std::io::{IsTerminal, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

/// The size past which the log rolls over.
pub const LIMIT: u64 = 5 * 1024 * 1024;
pub const FILE_NAME: &str = "whispy2.log";

struct Open {
    file: File,
    size: u64,
}

pub struct Logger {
    directory: PathBuf,
    limit: u64,
    /// Also print to stderr: set when stderr is a terminal, so `cargo run`
    /// stays readable.
    mirror: bool,
    open: Mutex<Option<Open>>,
}

impl Logger {
    /// Nothing is opened until the first line, so a read-only home only costs
    /// the file, never the app.
    pub fn new(directory: PathBuf, limit: u64, mirror: bool) -> Logger {
        Logger {
            directory,
            limit,
            mirror,
            open: Mutex::new(None),
        }
    }

    pub fn path(&self) -> PathBuf {
        self.directory.join(FILE_NAME)
    }

    pub fn line(&self, message: &str) {
        let line = format!("{} {message}\n", rfc3339_utc(unix_now()));
        // A poisoned lock only means another thread panicked mid-line.
        let mut open = self.open.lock().unwrap_or_else(|error| error.into_inner());
        if let Err(error) = self.write(&mut open, line.as_bytes()) {
            // The file is unusable: say so on the terminal, if any, and retry
            // from scratch on the next line.
            *open = None;
            if self.mirror {
                mirror_to_stderr(&format!("log file unavailable: {error}"));
            }
        }
        if self.mirror {
            mirror_to_stderr(message);
        }
    }

    fn write(&self, open: &mut Option<Open>, bytes: &[u8]) -> std::io::Result<()> {
        if open.is_none() {
            ensure_private_dir(&self.directory)?;
            *open = Some(self.open_file()?);
        }
        let current = open.as_mut().expect("opened above");
        // `size > 0`: a single line longer than the limit must not rotate an empty file forever.
        if current.size > 0 && current.size + bytes.len() as u64 > self.limit {
            *open = None;
            fs::rename(self.path(), self.directory.join(format!("{FILE_NAME}.1")))?;
            *open = Some(self.open_file()?);
        }
        let current = open.as_mut().expect("opened above");
        current.file.write_all(bytes)?;
        current.size += bytes.len() as u64;
        Ok(())
    }

    fn open_file(&self) -> std::io::Result<Open> {
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .mode(0o600)
            .open(self.path())?;
        let size = file.metadata()?.len();
        Ok(Open { file, size })
    }
}

static GLOBAL: OnceLock<Logger> = OnceLock::new();

/// Installs the process-wide logger. Call once, first thing in `main`; a second call is ignored.
pub fn init(directory: PathBuf) {
    let mirror = std::io::stderr().is_terminal();
    let _ = GLOBAL.set(Logger::new(directory, LIMIT, mirror));
}

/// Logs one line. Before [`init`] (and in tests) it goes to stderr only.
pub fn line(message: &str) {
    match GLOBAL.get() {
        Some(logger) => logger.line(message),
        None => mirror_to_stderr(message),
    }
}

/// The only `eprintln!` of the crate: the terminal mirror.
fn mirror_to_stderr(message: &str) {
    eprintln!("[whispy2] {message}");
}

/// Creates `path` (and missing parents) with mode 0700. An existing directory
/// keeps its mode: with `WHISPY_V2_SOCKET=/tmp/x.sock`, `/tmp` is not ours to chmod.
pub fn ensure_private_dir(path: &Path) -> std::io::Result<()> {
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(path)
}

pub fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs())
        .unwrap_or_default()
}

/// `2023-11-14T22:13:20Z`. Civil-from-days after Howard Hinnant's algorithm:
/// no date crate for one format.
pub fn rfc3339_utc(unix_seconds: u64) -> String {
    let days = unix_seconds / 86_400;
    let seconds_of_day = unix_seconds % 86_400;
    let z = days + 719_468;
    let era = z / 146_097;
    let day_of_era = z - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month = if month_index < 10 {
        month_index + 3
    } else {
        month_index - 9
    };
    let year = year_of_era + era * 400 + u64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        seconds_of_day / 3_600,
        seconds_of_day % 3_600 / 60,
        seconds_of_day % 60
    )
}

#[cfg(test)]
pub(crate) mod testing {
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU32, Ordering};

    /// A fresh, empty directory under the system temp dir.
    pub fn temp_dir(label: &str) -> PathBuf {
        static COUNTER: AtomicU32 = AtomicU32::new(0);
        let path = std::env::temp_dir().join(format!(
            "whispy2-test-{}-{}-{label}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::SeqCst)
        ));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(&path).unwrap();
        path
    }
}

#[cfg(test)]
mod tests {
    use super::testing::temp_dir;
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn timestamps_are_rfc3339_utc() {
        assert_eq!(rfc3339_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(rfc3339_utc(1_700_000_000), "2023-11-14T22:13:20Z");
        // A leap day.
        assert_eq!(rfc3339_utc(1_709_164_800), "2024-02-29T00:00:00Z");
    }

    #[test]
    fn lines_are_appended_to_a_private_file_in_a_private_directory() {
        let root = temp_dir("log-private");
        let directory = root.join("v2");
        let logger = Logger::new(directory.clone(), LIMIT, false);
        logger.line("first");
        logger.line("second");
        let text = fs::read_to_string(logger.path()).unwrap();
        assert_eq!(text.lines().count(), 2);
        assert!(text.lines().next().unwrap().ends_with(" first"));
        let mode = |path: &Path| fs::metadata(path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode(&directory), 0o700);
        assert_eq!(mode(&logger.path()), 0o600);
    }

    #[test]
    fn a_write_that_would_pass_the_limit_rotates_the_log() {
        let directory = temp_dir("log-rotate");
        let logger = Logger::new(directory.clone(), 200, false);
        let message = "x".repeat(60);
        for _ in 0..3 {
            logger.line(&message);
        }
        // The line was ~90 bytes: two fit, the third rotated.
        let rotated = directory.join("whispy2.log.1");
        assert_eq!(fs::read_to_string(&rotated).unwrap().lines().count(), 2);
        assert_eq!(
            fs::read_to_string(logger.path()).unwrap().lines().count(),
            1
        );
        // A second rotation replaces the previous copy.
        for _ in 0..2 {
            logger.line(&message);
        }
        assert_eq!(fs::read_to_string(&rotated).unwrap().lines().count(), 2);
    }

    #[test]
    fn an_unwritable_directory_does_not_panic() {
        let blocker = temp_dir("log-blocked").join("file");
        fs::write(&blocker, "").unwrap();
        // The "directory" is a file: every open fails.
        Logger::new(blocker, LIMIT, false).line("lost, but harmless");
    }
}

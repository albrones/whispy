//! Is Whispy V1 running? Then Fn is its key, and V2 stays out of the way.
//!
//! Two signs, either one is enough: something listens on V1's API port
//! (the bind is V1's single-instance lock, whether it runs from the bundle or
//! from `whispy_daemon.py`), or a process runs V1 (the bundle holds Fn before
//! its API is up, and still does if the port moved). On macOS that process runs
//! the bundle's executable; on Linux, Python with `whispy_daemon.py`.

use std::net::{Ipv4Addr, SocketAddr, TcpStream};
use std::time::Duration;

/// V1's API port (`src/whispy/api/server.py`).
pub const V1_PORT: u16 = 9090;
/// The V1 bundle's executable, as `make app` and `install.sh` build it.
pub const V1_EXECUTABLE_SUFFIX: &str = "/Whispy.app/Contents/MacOS/Whispy";
/// V1's daemon script, what its `systemd --user` unit runs under Linux.
pub const V1_DAEMON_SCRIPT: &str = "whispy_daemon.py";

const CONNECT_TIMEOUT: Duration = Duration::from_millis(200);

pub fn is_running() -> bool {
    is_port_open(V1_PORT) || process_paths().iter().any(|path| is_v1_executable(path))
}

/// `path` is an executable path (macOS) or one argument of a command line (Linux).
pub fn is_v1_executable(path: &str) -> bool {
    path.ends_with(V1_EXECUTABLE_SUFFIX) || path.ends_with(V1_DAEMON_SCRIPT)
}

fn is_port_open(port: u16) -> bool {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    TcpStream::connect_timeout(&address, CONNECT_TIMEOUT).is_ok()
}

/// The arguments of every process this user can see (`/proc/<pid>/cmdline`).
#[cfg(target_os = "linux")]
fn process_paths() -> Vec<String> {
    let Ok(entries) = std::fs::read_dir("/proc") else {
        return Vec::new();
    };
    entries
        .flatten()
        .filter(|entry| entry.file_name().to_string_lossy().parse::<u32>().is_ok())
        .filter_map(|entry| std::fs::read(entry.path().join("cmdline")).ok())
        .flat_map(|cmdline| {
            cmdline
                .split(|byte| *byte == 0)
                .filter(|argument| !argument.is_empty())
                .map(|argument| String::from_utf8_lossy(argument).into_owned())
                .collect::<Vec<_>>()
        })
        .collect()
}

/// Executable paths of the processes this user can see.
#[cfg(target_os = "macos")]
fn process_paths() -> Vec<String> {
    let mut pids = vec![0 as libc::pid_t; 4096];
    let buffer_size = (pids.len() * std::mem::size_of::<libc::pid_t>()) as libc::c_int;
    // SAFETY: the buffer holds `buffer_size` bytes; the call writes at most that.
    let count = unsafe { libc::proc_listallpids(pids.as_mut_ptr().cast(), buffer_size) };
    if count <= 0 {
        return Vec::new();
    }
    pids.truncate(count as usize);
    pids.into_iter().filter_map(executable_path).collect()
}

#[cfg(target_os = "macos")]
fn executable_path(pid: libc::pid_t) -> Option<String> {
    let mut buffer = vec![0u8; libc::PROC_PIDPATHINFO_MAXSIZE as usize];
    // SAFETY: the buffer holds PROC_PIDPATHINFO_MAXSIZE bytes, the size passed.
    let length =
        unsafe { libc::proc_pidpath(pid, buffer.as_mut_ptr().cast(), buffer.len() as u32) };
    if length <= 0 {
        return None;
    }
    buffer.truncate(length as usize);
    String::from_utf8(buffer).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn the_v1_bundle_is_recognised_and_v2_is_not() {
        assert!(is_v1_executable(
            "/Applications/Whispy.app/Contents/MacOS/Whispy"
        ));
        assert!(is_v1_executable(
            "/Users/me/Whispy/dist/Whispy.app/Contents/MacOS/Whispy"
        ));
        assert!(!is_v1_executable(
            "/Users/me/Whispy/v2/target/release/whispy2"
        ));
        assert!(!is_v1_executable(
            "/Applications/Whispy2.app/Contents/MacOS/Whispy2"
        ));
        assert!(is_v1_executable("/home/me/whispy/whispy_daemon.py"));
        assert!(!is_v1_executable(
            "/home/me/whispy/v2/target/release/whispy2"
        ));
    }

    #[test]
    fn a_listening_port_is_seen_and_a_closed_one_is_not() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(is_port_open(port));
        drop(listener);
        assert!(!is_port_open(port));
    }

    #[test]
    fn this_test_process_is_listed() {
        let own = std::env::current_exe().unwrap();
        let paths = process_paths();
        assert!(
            // Linux lists argv[0], which may be relative: the file name is enough.
            paths
                .iter()
                .any(|path| std::path::Path::new(path).file_name() == own.file_name()),
            "{} not among {} processes",
            own.display(),
            paths.len()
        );
    }
}

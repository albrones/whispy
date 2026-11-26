//! whispy2: the composition root of the platform this is built for, or, with
//! `send <request>`, a one-shot client of a running V2's control socket.

use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if let [command, request] = args.as_slice() {
        if command == "send" {
            return send(request);
        }
    }
    #[cfg(target_os = "macos")]
    whispy2::mac::app::run();
    #[cfg(target_os = "linux")]
    whispy2::linux::app::run();
    ExitCode::SUCCESS
}

/// Prints the reply. Exit 0 for an answer, 1 for an error or refusal reply,
/// 2 when no V2 answers on the socket.
fn send(request: &str) -> ExitCode {
    use whispy2::control;
    let Some(path) = control::default_path() else {
        eprintln!("whispy2: no HOME, so no control socket");
        return ExitCode::from(2);
    };
    match control::send(&path, request) {
        Ok(reply) => {
            println!("{reply}");
            if control::is_failure(&reply) {
                ExitCode::FAILURE
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(error) => {
            eprintln!(
                "whispy2: Whispy V2 is not answering on {} ({error})",
                path.display()
            );
            ExitCode::from(2)
        }
    }
}

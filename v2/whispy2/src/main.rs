//! whispy2: the composition root of the platform this is built for.

fn main() {
    #[cfg(target_os = "macos")]
    whispy2::mac::app::run();
    #[cfg(target_os = "linux")]
    whispy2::linux::app::run();
}

//! Which kind of graphical session V2 runs in, read from the environment.
//!
//! It decides three things: whether V2 listens to the trigger key itself (X11)
//! or leaves it to the compositor's binding (Wayland), which backend enigo
//! types through, and whether the tray icon is shown (X11 only, as in V1).

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Session {
    X11,
    Wayland,
    /// No display at all (a text console, a service started too early).
    None,
}

impl Session {
    /// The current process's session.
    pub fn current() -> Session {
        let var = |name: &str| std::env::var(name).ok().filter(|value| !value.is_empty());
        Session::from_env(
            var("XDG_SESSION_TYPE").as_deref(),
            var("WAYLAND_DISPLAY").is_some(),
            var("DISPLAY").is_some(),
        )
    }

    /// `XDG_SESSION_TYPE` wins when it names x11 or wayland; otherwise a
    /// Wayland socket wins over `DISPLAY`, which XWayland also sets.
    pub fn from_env(session_type: Option<&str>, wayland_display: bool, display: bool) -> Session {
        match session_type {
            Some("x11") => Session::X11,
            Some("wayland") => Session::Wayland,
            _ if wayland_display => Session::Wayland,
            _ if display => Session::X11,
            _ => Session::None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Session::X11 => "X11",
            Session::Wayland => "Wayland",
            Session::None => "no display",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_session_type_decides_first() {
        assert_eq!(Session::from_env(Some("x11"), true, true), Session::X11);
        assert_eq!(
            Session::from_env(Some("wayland"), false, true),
            Session::Wayland
        );
    }

    #[test]
    fn without_a_session_type_a_wayland_socket_beats_xwayland() {
        assert_eq!(Session::from_env(None, true, true), Session::Wayland);
        assert_eq!(Session::from_env(Some("tty"), false, true), Session::X11);
        assert_eq!(Session::from_env(None, false, false), Session::None);
    }
}

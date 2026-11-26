//! Linux adapters: the trigger key under X11, typing through enigo, the X11
//! tray icon and desktop notifications; [`app`] wires them.
//!
//! Under Wayland no client may listen to a global key: the compositor's key
//! binding drives the control socket (`~/.whispy/v2/control.sock`) instead.

pub mod app;
pub mod inserter;
pub mod notify;
pub mod session;
pub mod surface;
pub mod tray;
pub mod x11_trigger;

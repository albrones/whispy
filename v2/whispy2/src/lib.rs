//! Whispy V2, the app: hold the trigger key to dictate, release to insert.
//!
//! - [`machine`]: the dictation state machine, pure.
//! - [`controller`]: runs it against a microphone, the pipeline and an inserter (ports).
//! - [`mac`]: the macOS adapters behind those ports, and the menu bar.
//! - [`linux`]: the Linux adapters (X11 key, enigo, tray icon, notifications).
//! - [`microphone`]: the default input device through cpal, both platforms.
//! - [`control`]: the local socket that drives V2 and keeps it single.
//! - [`feedback`]: the indicator and alert sound, behind a port.
//! - [`journal`] and [`log`]: what V2 records about its dictations and itself.
//! - [`update`]: checks for a newer release and installs it from the menu.
//! - [`v1`]: tells whether Whispy V1 is running, so only one of them listens to Fn.

pub mod control;
pub mod controller;
pub mod feedback;
pub mod journal;
#[cfg(target_os = "linux")]
pub mod linux;
pub mod log;
#[cfg(target_os = "macos")]
pub mod mac;
pub mod machine;
pub mod menu_logic;
pub mod menu_model;
pub mod microphone;
pub mod pill_geometry;
pub mod resample;
pub mod settings;
pub mod theme;
pub mod title_anim;
pub mod trigger_key;
pub mod update;
pub mod v1;

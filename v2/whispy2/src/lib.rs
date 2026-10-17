//! Whispy V2, the macOS app: hold Fn to dictate, release to insert.
//!
//! - [`machine`]: the dictation state machine, pure.
//! - [`controller`]: runs it against a microphone, the pipeline and an inserter (ports).
//! - [`mac`]: the macOS adapters behind those ports, and the menu bar.
//! - [`v1`]: tells whether Whispy V1 is running, so only one of them listens to Fn.

pub mod controller;
pub mod mac;
pub mod machine;
pub mod resample;
pub mod v1;

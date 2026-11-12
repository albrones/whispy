//! The trigger key (Fn by default, or any of V1's keys), read by a listen-only
//! CGEventTap (needs Input Monitoring).
//!
//! What an event means is decided by [`crate::trigger_key`]: a modifier's state
//! is read off the flags of each flagsChanged event, absolute, so a missed event
//! cannot invert later ones (V1's diff-based decoding could). The callback only
//! decodes and forwards: macOS disables a tap whose callback is slow.

use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Instant;

use core_foundation::base::TCFType;
use core_foundation::mach_port::CFMachPortRef;
use core_foundation::runloop::{kCFRunLoopCommonModes, CFRunLoop};
use core_graphics::event::{
    CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement, CGEventType,
    CallbackResult, EventField,
};

use crate::machine::Event;
use crate::trigger_key::{self, Edge, EventKind};

pub use crate::trigger_key::FN_KEYCODE;

/// kCGEventSourceStateHIDSystemState: the hardware's view of the keys.
const HID_SYSTEM_STATE: i32 = 1;

extern "C" {
    fn CGEventTapIsEnabled(tap: CFMachPortRef) -> bool;
    fn CGEventTapEnable(tap: CFMachPortRef, enable: bool);
    fn CGEventSourceFlagsState(state_id: i32) -> u64;
    fn CGEventSourceKeyState(state_id: i32, key: u16) -> bool;
    fn CGPreflightListenEventAccess() -> bool;
    fn CGRequestListenEventAccess() -> bool;
}

/// A tap disabled again on every beat is logged once, then once a minute at
/// the 1 s housekeeping beat: without Input Monitoring the tap of an installed
/// bundle was seen disabled every second, one log line each.
const REPEAT_REPORT_EVERY: u32 = 60;

/// The trigger's keycode, shared with the tap's callback: a menu change swaps
/// the key without recreating the tap.
#[derive(Clone)]
pub struct TriggerKeyHandle(Arc<AtomicI64>);

impl TriggerKeyHandle {
    pub fn set(&self, keycode: i64) {
        self.0.store(keycode, Ordering::SeqCst);
    }

    pub fn get(&self) -> i64 {
        self.0.load(Ordering::SeqCst)
    }
}

/// The installed tap. Dropping it removes the tap.
pub struct TriggerTap {
    _tap: CGEventTap<'static>,
    pub health: TapHealth,
    pub key: TriggerKeyHandle,
}

/// What the housekeeping thread needs to keep the tap alive.
#[derive(Clone)]
pub struct TapHealth {
    /// The tap's mach port, as an address: CGEventTapIsEnabled and
    /// CGEventTapEnable may be called from any thread.
    port: usize,
    key: TriggerKeyHandle,
    is_trigger_held: Arc<AtomicBool>,
    /// Consecutive beats that found the tap disabled.
    disabled_beats: Arc<AtomicU32>,
}

// SAFETY: `port` is only handed to CGEventTapIsEnabled/CGEventTapEnable, which
// are thread-safe, and the port outlives the process's use of it (the tap
// lives until main returns).
unsafe impl Send for TapHealth {}

const NOT_GRANTED: &str =
    "The trigger key is not available: grant Input Monitoring to Whispy V2 (or to the \
     terminal that launched whispy2) in System Settings → Privacy & Security → Input Monitoring, \
     then quit and reopen it.";

/// Installs the tap on the main run loop; `forward` receives the key events.
/// `keycode` is the initial trigger. Fails when Input Monitoring is not granted.
pub fn install(
    keycode: i64,
    forward: impl Fn(Event) + Send + 'static,
) -> Result<TriggerTap, String> {
    // Without Input Monitoring a listen-only tap may still be created, then
    // sees nothing and is disabled over and over: ask first. The request adds
    // the app to the Input Monitoring list (and prompts once); macOS applies a
    // grant only to a relaunched process.
    // SAFETY: plain CoreGraphics calls without arguments (macOS 10.15+).
    if !unsafe { CGPreflightListenEventAccess() } {
        unsafe { CGRequestListenEventAccess() };
        return Err(NOT_GRANTED.to_string());
    }
    let key = TriggerKeyHandle(Arc::new(AtomicI64::new(keycode)));
    let callback_key = key.clone();
    let is_trigger_held = Arc::new(AtomicBool::new(false));
    let held = Arc::clone(&is_trigger_held);
    let tap = CGEventTap::new(
        CGEventTapLocation::Session,
        CGEventTapPlacement::HeadInsertEventTap,
        CGEventTapOptions::ListenOnly,
        vec![
            CGEventType::FlagsChanged,
            CGEventType::KeyDown,
            CGEventType::KeyUp,
        ],
        move |_proxy, event_type, event| {
            let kind = match event_type {
                CGEventType::FlagsChanged => EventKind::FlagsChanged,
                CGEventType::KeyDown => EventKind::KeyDown,
                CGEventType::KeyUp => EventKind::KeyUp,
                _ => return CallbackResult::Keep,
            };
            let trigger = callback_key.get();
            let pressed = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE);
            let is_autorepeat =
                event.get_integer_value_field(EventField::KEYBOARD_EVENT_AUTOREPEAT) != 0;
            let flags = event.get_flags().bits();
            match trigger_key::decode(trigger, pressed, kind, flags, is_autorepeat) {
                Some(edge) => {
                    held.store(edge == Edge::Down, Ordering::SeqCst);
                    let now = Instant::now();
                    forward(match edge {
                        Edge::Down => Event::TriggerDown(now),
                        Edge::Up => Event::TriggerUp(now),
                    });
                }
                // Another key while the trigger is held; never the trigger's own.
                None if kind == EventKind::KeyDown
                    && pressed != trigger
                    && held.load(Ordering::SeqCst) =>
                {
                    forward(Event::OtherKeyDown)
                }
                None => {}
            }
            CallbackResult::Keep
        },
    )
    .map_err(|()| NOT_GRANTED.to_string())?;
    let source = tap
        .mach_port()
        .create_runloop_source(0)
        .map_err(|()| "the trigger key tap could not be attached to the run loop".to_string())?;
    // SAFETY: kCFRunLoopCommonModes is a constant CFString provided by CoreFoundation.
    CFRunLoop::get_main().add_source(&source, unsafe { kCFRunLoopCommonModes });
    tap.enable();
    let port = tap.mach_port().as_concrete_TypeRef() as usize;
    Ok(TriggerTap {
        _tap: tap,
        health: TapHealth {
            port,
            key: key.clone(),
            is_trigger_held,
            disabled_beats: Arc::new(AtomicU32::new(0)),
        },
        key,
    })
}

impl TapHealth {
    /// Re-enables a tap macOS disabled (slow callback, heavy input) and, if the
    /// trigger was released meanwhile, returns the release the tap never saw. V1
    /// lost such releases and stayed stuck recording.
    pub fn revive(&self) -> Option<Event> {
        let port = self.port as CFMachPortRef;
        // SAFETY: `port` is the live tap's mach port (see `TapHealth`).
        if unsafe { CGEventTapIsEnabled(port) } {
            self.disabled_beats.store(0, Ordering::SeqCst);
            return None;
        }
        unsafe { CGEventTapEnable(port, true) };
        let beats = self.disabled_beats.fetch_add(1, Ordering::SeqCst);
        if beats.is_multiple_of(REPEAT_REPORT_EVERY) {
            crate::log::line(&format!(
                "the trigger key tap was disabled by macOS; re-enabled ({} time(s) in a row)",
                beats + 1
            ));
        }
        let keycode = self.key.get();
        // SAFETY: plain CoreGraphics state queries.
        let is_down_now = match trigger_key::modifier_is_down(keycode, unsafe {
            CGEventSourceFlagsState(HID_SYSTEM_STATE)
        }) {
            Some(is_down) => is_down,
            None => u16::try_from(keycode)
                .is_ok_and(|code| unsafe { CGEventSourceKeyState(HID_SYSTEM_STATE, code) }),
        };
        let was_down = self.is_trigger_held.swap(is_down_now, Ordering::SeqCst);
        (was_down && !is_down_now).then(|| Event::TriggerUp(Instant::now()))
    }
}

//! The Fn key, read by a listen-only CGEventTap (needs Input Monitoring).
//!
//! Fn is keycode 63 and its state is the secondary-Fn flag bit, read on each
//! flagsChanged event: absolute, so a missed event cannot invert later ones
//! (V1's diff-based decoding of modifier triggers could). The callback only
//! decodes and forwards: macOS disables a tap whose callback is slow.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;

use core_foundation::base::TCFType;
use core_foundation::mach_port::CFMachPortRef;
use core_foundation::runloop::{kCFRunLoopCommonModes, CFRunLoop};
use core_graphics::event::{
    CGEventFlags, CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventType, CallbackResult, EventField,
};

use crate::machine::Event;

/// Fn / Globe.
pub const FN_KEYCODE: i64 = 63;
/// kCGEventSourceStateHIDSystemState: the hardware's view of the keys.
const HID_SYSTEM_STATE: i32 = 1;

extern "C" {
    fn CGEventTapIsEnabled(tap: CFMachPortRef) -> bool;
    fn CGEventTapEnable(tap: CFMachPortRef, enable: bool);
    fn CGEventSourceFlagsState(state_id: i32) -> u64;
}

/// The installed tap. Dropping it removes the tap.
pub struct FnKey {
    _tap: CGEventTap<'static>,
    pub health: TapHealth,
}

/// What the housekeeping thread needs to keep the tap alive.
#[derive(Clone)]
pub struct TapHealth {
    /// The tap's mach port, as an address: CGEventTapIsEnabled and
    /// CGEventTapEnable may be called from any thread.
    port: usize,
    is_fn_held: Arc<AtomicBool>,
}

// SAFETY: `port` is only handed to CGEventTapIsEnabled/CGEventTapEnable, which
// are thread-safe, and the port outlives the process's use of it (the tap
// lives until main returns).
unsafe impl Send for TapHealth {}

/// Installs the tap on the main run loop; `forward` receives the key events.
/// Fails when Input Monitoring is not granted.
pub fn install(forward: impl Fn(Event) + Send + 'static) -> Result<FnKey, String> {
    let is_fn_held = Arc::new(AtomicBool::new(false));
    let held = Arc::clone(&is_fn_held);
    let tap = CGEventTap::new(
        CGEventTapLocation::Session,
        CGEventTapPlacement::HeadInsertEventTap,
        CGEventTapOptions::ListenOnly,
        vec![CGEventType::FlagsChanged, CGEventType::KeyDown],
        move |_proxy, event_type, event| {
            match event_type {
                CGEventType::FlagsChanged => {
                    let keycode = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE);
                    if keycode == FN_KEYCODE {
                        let is_down = event
                            .get_flags()
                            .contains(CGEventFlags::CGEventFlagSecondaryFn);
                        held.store(is_down, Ordering::SeqCst);
                        let now = Instant::now();
                        forward(if is_down {
                            Event::FnDown(now)
                        } else {
                            Event::FnUp(now)
                        });
                    }
                }
                CGEventType::KeyDown if held.load(Ordering::SeqCst) => forward(Event::OtherKeyDown),
                _ => {}
            }
            CallbackResult::Keep
        },
    )
    .map_err(|()| {
        "Fn is not available: grant Input Monitoring to the app that launched whispy2 \
         (System Settings → Privacy & Security → Input Monitoring), then restart whispy2."
            .to_string()
    })?;
    let source = tap
        .mach_port()
        .create_runloop_source(0)
        .map_err(|()| "the Fn key tap could not be attached to the run loop".to_string())?;
    // SAFETY: kCFRunLoopCommonModes is a constant CFString provided by CoreFoundation.
    CFRunLoop::get_main().add_source(&source, unsafe { kCFRunLoopCommonModes });
    tap.enable();
    let port = tap.mach_port().as_concrete_TypeRef() as usize;
    Ok(FnKey {
        _tap: tap,
        health: TapHealth { port, is_fn_held },
    })
}

impl TapHealth {
    /// Re-enables a tap macOS disabled (slow callback, heavy input) and, if Fn
    /// was released meanwhile, returns the release the tap never saw. V1 lost
    /// such releases and stayed stuck recording.
    pub fn revive(&self) -> Option<Event> {
        let port = self.port as CFMachPortRef;
        // SAFETY: `port` is the live tap's mach port (see `TapHealth`).
        if unsafe { CGEventTapIsEnabled(port) } {
            return None;
        }
        unsafe { CGEventTapEnable(port, true) };
        eprintln!("[whispy2] the Fn tap was disabled by macOS; re-enabled");
        let is_down_now = unsafe { CGEventSourceFlagsState(HID_SYSTEM_STATE) }
            & CGEventFlags::CGEventFlagSecondaryFn.bits()
            != 0;
        let was_down = self.is_fn_held.swap(is_down_now, Ordering::SeqCst);
        (was_down && !is_down_now).then(|| Event::FnUp(Instant::now()))
    }
}

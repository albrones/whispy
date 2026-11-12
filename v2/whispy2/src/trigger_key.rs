//! Decoding of the trigger key's events, pure and portable: no CoreGraphics
//! type in any signature, so the rules are tested without a keyboard.
//!
//! V1's `event_decode.py` is the reference. A modifier trigger (Fn, Right
//! Command, Right Option, ...) arrives as `flagsChanged` with no key-up, so its
//! state is read off the flag bits of that one event, never from history: a
//! missed event cannot invert the ones after it. Any other key arrives as
//! `keyDown`/`keyUp`, and the autorepeat of a held key is not a new press.

/// The kind of event the tap saw.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventKind {
    FlagsChanged,
    KeyDown,
    KeyUp,
}

/// What an event means for the trigger.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Edge {
    Down,
    Up,
}

/// Fn / Globe.
pub const FN_KEYCODE: i64 = 63;

/// CGEventFlagSecondaryFn.
const FN_FLAG: u64 = 0x80_0000;

// The side-agnostic modifier bits (CGEventFlags): one bit for the left and
// right key alike.
const SHIFT: u64 = 0x2_0000;
const CONTROL: u64 = 0x4_0000;
const OPTION: u64 = 0x8_0000;
const COMMAND: u64 = 0x10_0000;

// The device-dependent bits (IOLLEvent.h): one per physical key, which is what
// tells Right Option from Left Option when both set `OPTION`.
const DEVICE_LCTL: u64 = 0x1;
const DEVICE_LSHIFT: u64 = 0x2;
const DEVICE_RSHIFT: u64 = 0x4;
const DEVICE_LCMD: u64 = 0x8;
const DEVICE_RCMD: u64 = 0x10;
const DEVICE_LALT: u64 = 0x20;
const DEVICE_RALT: u64 = 0x40;
const DEVICE_RCTL: u64 = 0x2000;

/// A modifier key: its shared flag, its own device bit (0 when it has none, as
/// Fn) and the device bits of both sides of its family.
struct Modifier {
    shared: u64,
    device: u64,
    family: u64,
}

fn modifier(keycode: i64) -> Option<Modifier> {
    let family = |left: u64, right: u64| left | right;
    Some(match keycode {
        FN_KEYCODE => Modifier {
            shared: FN_FLAG,
            device: 0,
            family: 0,
        },
        54 => Modifier {
            shared: COMMAND,
            device: DEVICE_RCMD,
            family: family(DEVICE_LCMD, DEVICE_RCMD),
        },
        55 => Modifier {
            shared: COMMAND,
            device: DEVICE_LCMD,
            family: family(DEVICE_LCMD, DEVICE_RCMD),
        },
        61 => Modifier {
            shared: OPTION,
            device: DEVICE_RALT,
            family: family(DEVICE_LALT, DEVICE_RALT),
        },
        58 => Modifier {
            shared: OPTION,
            device: DEVICE_LALT,
            family: family(DEVICE_LALT, DEVICE_RALT),
        },
        60 => Modifier {
            shared: SHIFT,
            device: DEVICE_RSHIFT,
            family: family(DEVICE_LSHIFT, DEVICE_RSHIFT),
        },
        56 => Modifier {
            shared: SHIFT,
            device: DEVICE_LSHIFT,
            family: family(DEVICE_LSHIFT, DEVICE_RSHIFT),
        },
        62 => Modifier {
            shared: CONTROL,
            device: DEVICE_RCTL,
            family: family(DEVICE_LCTL, DEVICE_RCTL),
        },
        59 => Modifier {
            shared: CONTROL,
            device: DEVICE_LCTL,
            family: family(DEVICE_LCTL, DEVICE_RCTL),
        },
        _ => return None,
    })
}

/// Whether `keycode` is read from `flagsChanged` rather than key down/up.
pub fn is_modifier(keycode: i64) -> bool {
    modifier(keycode).is_some()
}

/// Whether the modifier `keycode` is down according to `flags`; `None` for a
/// key that is not a modifier. The same rule serves a `flagsChanged` event and
/// the live flags read when the tap is revived.
///
/// Its own device bit set means down. The shared bit clear means the modifier
/// is fully up. If the shared bit is set but our bit is not, the other side may
/// be what holds it: that is a release when the stream carries device bits at
/// all (some of the family's bits is set), and otherwise a keyboard or remapper
/// that sends none, where the event can only be a press.
pub fn modifier_is_down(keycode: i64, flags: u64) -> Option<bool> {
    let key = modifier(keycode)?;
    if key.device == 0 {
        return Some(flags & key.shared != 0);
    }
    Some(if flags & key.device != 0 {
        true
    } else if flags & key.shared == 0 {
        false
    } else {
        flags & key.family == 0
    })
}

/// The edge an event makes on the trigger key, if any.
pub fn decode(
    trigger: i64,
    keycode: i64,
    kind: EventKind,
    flags: u64,
    is_autorepeat: bool,
) -> Option<Edge> {
    if keycode != trigger {
        return None;
    }
    match (modifier_is_down(trigger, flags), kind) {
        (Some(is_down), EventKind::FlagsChanged) => {
            Some(if is_down { Edge::Down } else { Edge::Up })
        }
        // A modifier never arrives as a key event.
        (Some(_), _) => None,
        (None, EventKind::KeyDown) if !is_autorepeat => Some(Edge::Down),
        (None, EventKind::KeyUp) => Some(Edge::Up),
        (None, _) => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const RIGHT_COMMAND: i64 = 54;
    const LEFT_COMMAND: i64 = 55;
    const RIGHT_OPTION: i64 = 61;
    const F13: i64 = 105;

    fn flags_changed(trigger: i64, keycode: i64, flags: u64) -> Option<Edge> {
        decode(trigger, keycode, EventKind::FlagsChanged, flags, false)
    }

    #[test]
    fn right_command_goes_down_and_up_and_left_command_is_ignored() {
        let down = COMMAND | DEVICE_RCMD;
        assert_eq!(
            flags_changed(RIGHT_COMMAND, RIGHT_COMMAND, down),
            Some(Edge::Down)
        );
        assert_eq!(
            flags_changed(RIGHT_COMMAND, RIGHT_COMMAND, 0),
            Some(Edge::Up)
        );
        // The left key reports its own keycode: not the trigger.
        assert_eq!(
            flags_changed(RIGHT_COMMAND, LEFT_COMMAND, COMMAND | DEVICE_LCMD),
            None
        );
    }

    #[test]
    fn right_command_released_while_left_is_held_is_an_up() {
        // The shared bit stays set (left still down), our own device bit is gone.
        let flags = COMMAND | DEVICE_LCMD;
        assert_eq!(
            flags_changed(RIGHT_COMMAND, RIGHT_COMMAND, flags),
            Some(Edge::Up)
        );
    }

    #[test]
    fn a_keyboard_without_device_bits_still_reads_a_press() {
        assert_eq!(
            flags_changed(RIGHT_OPTION, RIGHT_OPTION, OPTION),
            Some(Edge::Down)
        );
        assert_eq!(flags_changed(RIGHT_OPTION, RIGHT_OPTION, 0), Some(Edge::Up));
    }

    #[test]
    fn fn_is_the_secondary_fn_flag() {
        assert_eq!(
            flags_changed(FN_KEYCODE, FN_KEYCODE, FN_FLAG),
            Some(Edge::Down)
        );
        assert_eq!(flags_changed(FN_KEYCODE, FN_KEYCODE, 0), Some(Edge::Up));
    }

    #[test]
    fn a_regular_key_uses_key_down_and_up() {
        assert_eq!(
            decode(F13, F13, EventKind::KeyDown, 0, false),
            Some(Edge::Down)
        );
        assert_eq!(decode(F13, F13, EventKind::KeyUp, 0, false), Some(Edge::Up));
        assert_eq!(decode(F13, 0, EventKind::KeyDown, 0, false), None);
        assert_eq!(decode(F13, F13, EventKind::FlagsChanged, 0, false), None);
    }

    #[test]
    fn the_autorepeat_of_a_held_key_is_not_a_new_press() {
        assert_eq!(decode(F13, F13, EventKind::KeyDown, 0, true), None);
    }

    #[test]
    fn a_modifier_trigger_ignores_key_events() {
        assert_eq!(
            decode(RIGHT_COMMAND, RIGHT_COMMAND, EventKind::KeyDown, 0, false),
            None
        );
    }

    #[test]
    fn live_flags_read_the_same_way() {
        assert_eq!(
            modifier_is_down(RIGHT_COMMAND, COMMAND | DEVICE_RCMD),
            Some(true)
        );
        assert_eq!(modifier_is_down(RIGHT_COMMAND, 0), Some(false));
        assert_eq!(modifier_is_down(F13, 0), None);
    }
}

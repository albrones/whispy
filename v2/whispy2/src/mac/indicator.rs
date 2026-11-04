//! The floating indicator: a small non-activating panel at the bottom centre
//! of the screen with the mouse, showing "Recording" with a live level or
//! "Transcribing…". It never takes focus: the user is typing elsewhere.
//!
//! AppKit objects live on the main thread only; [`PanelFeedback`] is a
//! zero-size `Send` handle whose methods hop to the main queue.

use std::cell::RefCell;

use dispatch2::DispatchQueue;
use objc2::rc::Retained;
use objc2::{MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{
    NSBackingStoreType, NSColor, NSEvent, NSLevelIndicator, NSLevelIndicatorStyle, NSPanel,
    NSScreen, NSSound, NSStatusWindowLevel, NSTextField, NSWindowCollectionBehavior,
    NSWindowStyleMask,
};
use objc2_foundation::{NSPoint, NSRect, NSSize, NSString};

use crate::feedback::{Feedback, Phase};

const PANEL_WIDTH: f64 = 180.0;
const PANEL_HEIGHT: f64 = 56.0;
/// Distance between the bottom of the visible screen and the panel.
const BOTTOM_MARGIN: f64 = 40.0;
const PADDING: f64 = 12.0;
const LABEL_HEIGHT: f64 = 18.0;
const METER_HEIGHT: f64 = 12.0;

struct Panel {
    panel: Retained<NSPanel>,
    label: Retained<NSTextField>,
    meter: Retained<NSLevelIndicator>,
}

thread_local! {
    static PANEL: RefCell<Option<Panel>> = const { RefCell::new(None) };
}

/// The `Feedback` of the macOS app. Holds nothing: the panel is main-thread state.
pub struct PanelFeedback;

impl Feedback for PanelFeedback {
    fn show(&mut self, phase: Phase) {
        on_main(move |mtm| PANEL.with(|cell| show_phase(mtm, &mut cell.borrow_mut(), phase)));
    }

    fn level(&mut self, level: f32) {
        let value = meter_value(level);
        on_main(move |_| {
            PANEL.with(|cell| {
                if let Some(panel) = cell.borrow().as_ref() {
                    panel.meter.setDoubleValue(value);
                }
            })
        });
    }

    fn alert(&mut self) {
        // The deaf-take failure sound of V1.
        on_main(|_| {
            if let Some(sound) = NSSound::soundNamed(&NSString::from_str("Basso")) {
                sound.play();
            }
        });
    }
}

fn on_main(work: impl FnOnce(MainThreadMarker) + Send + 'static) {
    DispatchQueue::main().exec_async(move || {
        let mtm = MainThreadMarker::new().expect("the main queue runs on the main thread");
        work(mtm);
    });
}

fn show_phase(mtm: MainThreadMarker, slot: &mut Option<Panel>, phase: Phase) {
    if phase == Phase::Hidden {
        if let Some(panel) = slot.as_ref() {
            panel.panel.orderOut(None);
        }
        return;
    }
    let panel = slot.get_or_insert_with(|| build(mtm));
    let (text, is_recording) = match phase {
        Phase::Recording => ("Recording", true),
        _ => ("Transcribing\u{2026}", false),
    };
    panel.label.setStringValue(&NSString::from_str(text));
    panel.meter.setHidden(!is_recording);
    if is_recording {
        panel.meter.setDoubleValue(0.0);
        // Re-placed on each recording: the mouse may be on another screen.
        let frame = placement(visible_frame_under_mouse(mtm));
        panel.panel.setFrame_display(frame, false);
    }
    // Never makeKey / activate: the focus stays in the app being dictated into.
    panel.panel.orderFrontRegardless();
}

fn build(mtm: MainThreadMarker) -> Panel {
    let rect = NSRect::new(
        NSPoint::new(0.0, 0.0),
        NSSize::new(PANEL_WIDTH, PANEL_HEIGHT),
    );
    let panel = {
        NSPanel::initWithContentRect_styleMask_backing_defer(
            NSPanel::alloc(mtm),
            rect,
            NSWindowStyleMask::Borderless | NSWindowStyleMask::NonactivatingPanel,
            NSBackingStoreType::Buffered,
            false,
        )
    };
    // SAFETY: the panel is owned by the thread_local; AppKit must not release it on close.
    unsafe { panel.setReleasedWhenClosed(false) };
    panel.setLevel(NSStatusWindowLevel);
    panel.setCollectionBehavior(
        NSWindowCollectionBehavior::CanJoinAllSpaces
            | NSWindowCollectionBehavior::FullScreenAuxiliary
            | NSWindowCollectionBehavior::Stationary
            | NSWindowCollectionBehavior::IgnoresCycle,
    );
    panel.setIgnoresMouseEvents(true);
    panel.setHidesOnDeactivate(false);
    panel.setBecomesKeyOnlyIfNeeded(true);
    panel.setOpaque(false);
    // Plain translucent dark background: no layer or visual-effect view needed.
    panel.setBackgroundColor(Some(&NSColor::colorWithSRGBRed_green_blue_alpha(
        0.08, 0.08, 0.09, 0.88,
    )));

    let label = NSTextField::labelWithString(&NSString::from_str("Recording"), mtm);
    label.setTextColor(Some(&NSColor::whiteColor()));
    label.setFrame(NSRect::new(
        NSPoint::new(PADDING, PANEL_HEIGHT - PADDING - LABEL_HEIGHT),
        NSSize::new(PANEL_WIDTH - 2.0 * PADDING, LABEL_HEIGHT),
    ));
    let meter = NSLevelIndicator::new(mtm);
    meter.setLevelIndicatorStyle(NSLevelIndicatorStyle::ContinuousCapacity);
    meter.setMinValue(0.0);
    meter.setMaxValue(1.0);
    meter.setDoubleValue(0.0);
    meter.setFrame(NSRect::new(
        NSPoint::new(PADDING, PADDING),
        NSSize::new(PANEL_WIDTH - 2.0 * PADDING, METER_HEIGHT),
    ));
    if let Some(content) = panel.contentView() {
        content.addSubview(&label);
        content.addSubview(&meter);
    }
    Panel {
        panel,
        label,
        meter,
    }
}

/// The visible frame (menu bar and Dock excluded) of the screen holding the
/// mouse, or of the main screen.
fn visible_frame_under_mouse(mtm: MainThreadMarker) -> NSRect {
    let mouse = NSEvent::mouseLocation();
    let screens = NSScreen::screens(mtm);
    for screen in screens.iter() {
        let frame = screen.frame();
        if contains(frame, mouse.x, mouse.y) {
            return screen.visibleFrame();
        }
    }
    NSScreen::mainScreen(mtm)
        .map(|screen| screen.visibleFrame())
        .unwrap_or_else(|| NSRect::new(NSPoint::new(0.0, 0.0), NSSize::new(1440.0, 900.0)))
}

fn contains(frame: NSRect, x: f64, y: f64) -> bool {
    x >= frame.origin.x
        && x < frame.origin.x + frame.size.width
        && y >= frame.origin.y
        && y < frame.origin.y + frame.size.height
}

/// The panel rectangle: bottom-centre of a screen's visible frame.
fn placement(visible: NSRect) -> NSRect {
    NSRect::new(
        NSPoint::new(
            visible.origin.x + (visible.size.width - PANEL_WIDTH) / 2.0,
            visible.origin.y + BOTTOM_MARGIN,
        ),
        NSSize::new(PANEL_WIDTH, PANEL_HEIGHT),
    )
}

/// RMS (speech sits around 0.01 to 0.2) to the 0.0 to 1.0 meter. A square
/// root curve is a cheap stand-in for loudness perception: quiet speech still
/// moves the bar, and 0.125 RMS already fills it.
fn meter_value(rms: f32) -> f64 {
    f64::from((rms.max(0.0) * 8.0).sqrt().min(1.0))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_meter_curve_is_perceptual_and_bounded() {
        assert_eq!(meter_value(0.0), 0.0);
        assert_eq!(meter_value(-1.0), 0.0);
        assert_eq!(meter_value(1.0), 1.0);
        // Quiet speech is lifted well above a linear mapping.
        assert!(meter_value(0.01) > 0.25);
        assert!(meter_value(0.02) > meter_value(0.01));
        assert!((meter_value(0.125) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn the_panel_sits_bottom_centre_of_the_visible_frame() {
        // A second screen to the right, with a Dock of 70 pt at the bottom.
        let visible = NSRect::new(NSPoint::new(1440.0, 70.0), NSSize::new(1000.0, 800.0));
        let frame = placement(visible);
        assert_eq!(frame.origin.x, 1440.0 + (1000.0 - PANEL_WIDTH) / 2.0);
        assert_eq!(frame.origin.y, 70.0 + BOTTOM_MARGIN);
        assert_eq!(frame.size.width, PANEL_WIDTH);
    }

    #[test]
    fn a_point_is_on_the_screen_that_contains_it() {
        let frame = NSRect::new(NSPoint::new(-1000.0, 0.0), NSSize::new(1000.0, 800.0));
        assert!(contains(frame, -1.0, 10.0));
        assert!(!contains(frame, 0.0, 10.0));
    }
}

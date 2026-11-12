//! V1's recording pill, ported from `src/whispy/ui/waveform_window.py`: a
//! non-activating panel at the bottom centre of the main screen, hosting a
//! custom view that draws a rounded dark background and 11 level-reactive bars,
//! repainted at 30 fps by a timer that also fades the panel in and out.
//!
//! The geometry, colours and easing are the pure functions of
//! `pill_geometry`; this file only does AppKit. All AppKit objects and the
//! animation state live on the main thread; [`PillFeedback`] is a zero-size
//! `Send` handle whose methods hop to the main queue, as `menu_bar::show` does.

use std::cell::{Cell, RefCell};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Instant;

use dispatch2::DispatchQueue;
use objc2::rc::Retained;
use objc2::runtime::AnyObject;
use objc2::{define_class, msg_send, sel, MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{
    NSBackingStoreType, NSBezierPath, NSColor, NSPanel, NSScreen, NSScreenSaverWindowLevel,
    NSSound, NSView, NSWindowCollectionBehavior, NSWindowStyleMask,
};
use objc2_foundation::{NSObject, NSPoint, NSRect, NSSize, NSString, NSTimer};

use super::notify;
use crate::feedback::{Feedback, Phase};
use crate::log;
use crate::menu_model::Alert;
use crate::pill_geometry::{
    advance_phase, bar_color, bar_heights, bar_rects, fade_step, level_from_rms, pill_origin,
    smooth, Rect, BACKGROUND, BAR_WIDTH, FPS, HIDE_BELOW_ALPHA, PILL_HEIGHT, PILL_WIDTH,
};

/// V1 keeps the pill joining the active Space on every orderFront, so a
/// full-screen app frontmost at the start of a recording gets it.
fn overlay_behavior() -> NSWindowCollectionBehavior {
    NSWindowCollectionBehavior::MoveToActiveSpace
        | NSWindowCollectionBehavior::FullScreenAuxiliary
        | NSWindowCollectionBehavior::IgnoresCycle
}

/// The latest microphone level (V1's scale, 0 to 1) as `f32` bits, written by
/// the controller thread and read by the timer on the main thread.
static TARGET_LEVEL: AtomicU32 = AtomicU32::new(0);

struct Pill {
    panel: Retained<NSPanel>,
    /// Held so the timer's target outlives the timer (a timer retains its target, but be explicit).
    _view: Retained<PillView>,
    target: Retained<TimerTarget>,
    timer: Option<Retained<NSTimer>>,
    level: f64,
    phase: f64,
    last_frame: Instant,
    fade: f64,
    fade_target: f64,
}

thread_local! {
    static PILL: RefCell<Option<Pill>> = const { RefCell::new(None) };
    /// What `drawRect:` paints: (smoothed level, wobble phase). Separate from
    /// [`PILL`] so drawing never re-enters its borrow.
    static DRAW: Cell<(f64, f64)> = const { Cell::new((0.0, 0.0)) };
}

define_class!(
    // SAFETY: NSView has no subclassing requirements beyond overriding methods; PillView adds no ivars.
    #[unsafe(super(NSView))]
    #[thread_kind = MainThreadOnly]
    #[name = "Whispy2PillView"]
    struct PillView;

    impl PillView {
        // SAFETY: the signature matches `- (void)drawRect:(NSRect)dirtyRect`.
        #[unsafe(method(drawRect:))]
        fn draw_rect(&self, _dirty: NSRect) {
            let bounds = self.bounds();
            let (level, phase) = DRAW.with(Cell::get);
            let (width, height) = (bounds.size.width, bounds.size.height);

            // Rounded "pill" background.
            let radius = height / 2.0;
            let pill = NSBezierPath::bezierPathWithRoundedRect_xRadius_yRadius(
                bounds, radius, radius,
            );
            srgb(BACKGROUND).set();
            pill.fill();

            // Bars, centred horizontally and vertically.
            let rects = bar_rects(width, height, &bar_heights(level, phase));
            let color = srgb(bar_color(level));
            for (x, y, w, h) in rects {
                let bar = NSBezierPath::bezierPathWithRoundedRect_xRadius_yRadius(
                    rect((x, y, w, h)),
                    BAR_WIDTH / 2.0,
                    BAR_WIDTH / 2.0,
                );
                color.set();
                bar.fill();
            }
        }
    }
);

define_class!(
    // SAFETY: NSObject has no subclassing requirements; TimerTarget adds no ivars.
    #[unsafe(super(NSObject))]
    #[thread_kind = MainThreadOnly]
    #[name = "Whispy2PillTimerTarget"]
    struct TimerTarget;

    impl TimerTarget {
        // SAFETY: the signature matches an NSTimer selector, `- (void)tick:(NSTimer *)timer`.
        #[unsafe(method(tick:))]
        fn tick(&self, _timer: &NSTimer) {
            PILL.with(|cell| {
                if let Some(pill) = cell.borrow_mut().as_mut() {
                    pill.tick();
                }
            });
        }
    }
);

fn srgb((r, g, b, a): (f64, f64, f64, f64)) -> Retained<NSColor> {
    NSColor::colorWithSRGBRed_green_blue_alpha(r, g, b, a)
}

fn rect((x, y, w, h): Rect) -> NSRect {
    NSRect::new(NSPoint::new(x, y), NSSize::new(w, h))
}

impl Pill {
    fn build(mtm: MainThreadMarker) -> Pill {
        let frame = rect((0.0, 0.0, PILL_WIDTH, PILL_HEIGHT));
        // A non-activating floating panel: an accessory (menu bar) app can show
        // it over another app's full-screen Space without stealing focus.
        let panel = NSPanel::initWithContentRect_styleMask_backing_defer(
            NSPanel::alloc(mtm),
            frame,
            NSWindowStyleMask::Borderless | NSWindowStyleMask::NonactivatingPanel,
            NSBackingStoreType::Buffered,
            false,
        );
        // SAFETY: the panel is owned by the thread_local; AppKit must not release it on close.
        unsafe { panel.setReleasedWhenClosed(false) };
        panel.setFloatingPanel(true);
        panel.setBecomesKeyOnlyIfNeeded(true);
        panel.setHidesOnDeactivate(false);
        panel.setOpaque(false);
        panel.setBackgroundColor(Some(&NSColor::clearColor()));
        panel.setHasShadow(true);
        panel.setIgnoresMouseEvents(true);
        panel.setMovable(false);
        panel.setLevel(NSScreenSaverWindowLevel);
        panel.setCollectionBehavior(overlay_behavior());

        // SAFETY: plain allocation and `initWithFrame:` of an NSView subclass.
        let view: Retained<PillView> =
            unsafe { msg_send![PillView::alloc(mtm), initWithFrame: frame] };
        panel.setContentView(Some(&view));
        // SAFETY: plain allocation and `init` of an NSObject subclass.
        let target: Retained<TimerTarget> = unsafe { msg_send![TimerTarget::alloc(mtm), init] };
        Pill {
            panel,
            _view: view,
            target,
            timer: None,
            level: 0.0,
            phase: 0.0,
            last_frame: Instant::now(),
            fade: 0.0,
            fade_target: 0.0,
        }
    }

    fn start_animation(&mut self) {
        if self.timer.is_some() {
            return;
        }
        self.last_frame = Instant::now();
        let target: &AnyObject = &self.target;
        // SAFETY: `tick:` is implemented by TimerTarget, which the timer retains.
        let timer = unsafe {
            NSTimer::scheduledTimerWithTimeInterval_target_selector_userInfo_repeats(
                1.0 / FPS,
                target,
                sel!(tick:),
                None,
                true,
            )
        };
        self.timer = Some(timer);
    }

    fn stop_animation(&mut self) {
        if let Some(timer) = self.timer.take() {
            timer.invalidate();
        }
    }

    /// V1's `tick_`: smooth the level, advance the wobble, fade, repaint, and
    /// put the window away once it has faded out.
    fn tick(&mut self) {
        let now = Instant::now();
        let dt = now.duration_since(self.last_frame).as_secs_f64();
        self.last_frame = now;

        let target = f64::from(f32::from_bits(TARGET_LEVEL.load(Ordering::Relaxed)));
        self.level = smooth(self.level, target, dt);
        self.phase = advance_phase(self.phase, dt);
        self.fade = fade_step(self.fade, self.fade_target, dt);
        DRAW.with(|draw| draw.set((self.level, self.phase)));

        self.panel.setAlphaValue(self.fade);
        self.panel
            .contentView()
            .inspect(|view| view.setNeedsDisplay(true));

        if self.fade_target == 0.0 && self.fade < HIDE_BELOW_ALPHA {
            self.panel.orderOut(None);
            self.stop_animation();
        }
    }

    fn show(&mut self, mtm: MainThreadMarker) {
        // Re-applied on every show, as V1 found it must be: the active Space may
        // have changed (a full-screen app in front) since the last one.
        self.panel.setLevel(NSScreenSaverWindowLevel);
        self.panel.setCollectionBehavior(overlay_behavior());

        // The active screen each time; the first screen if there is no main one.
        let screen = NSScreen::mainScreen(mtm).or_else(|| NSScreen::screens(mtm).firstObject());
        let Some(screen) = screen else {
            log::line("pill: no screen available");
            return;
        };
        let visible = screen.visibleFrame();
        let (x, y) = pill_origin((
            visible.origin.x,
            visible.origin.y,
            visible.size.width,
            visible.size.height,
        ));
        self.panel.setFrameOrigin(NSPoint::new(x, y));

        // Start transparent and fade in through the timer.
        self.panel.setAlphaValue(0.0);
        self.fade_target = 1.0;
        self.panel.orderFrontRegardless();
        self.start_animation();
    }

    fn hide(&mut self) {
        // Fade out; the timer orders the window out once it is transparent.
        self.fade_target = 0.0;
    }
}

/// The `Feedback` of the macOS app. Holds nothing: the pill is main-thread
/// state and the level travels through [`TARGET_LEVEL`].
pub struct PillFeedback;

impl Feedback for PillFeedback {
    fn show(&mut self, phase: Phase) {
        match phase {
            Phase::Recording => on_main(|mtm| {
                PILL.with(|cell| {
                    cell.borrow_mut()
                        .get_or_insert_with(|| Pill::build(mtm))
                        .show(mtm)
                })
            }),
            Phase::Hidden => on_main(|_| {
                PILL.with(|cell| {
                    if let Some(pill) = cell.borrow_mut().as_mut() {
                        pill.hide();
                    }
                })
            }),
        }
    }

    fn level(&mut self, rms: f32) {
        let level = level_from_rms(f64::from(rms.max(0.0))) as f32;
        TARGET_LEVEL.store(level.to_bits(), Ordering::Relaxed);
    }

    fn alert(&mut self, alert: Alert) {
        // The deaf-take failure sound of V1, kept with its notification.
        if alert.subtitle == Alert::microphone_heard_nothing("").subtitle {
            on_main(|_| {
                if let Some(sound) = NSSound::soundNamed(&NSString::from_str("Basso")) {
                    sound.play();
                }
            });
        }
        notify::post(&alert);
    }
}

fn on_main(work: impl FnOnce(MainThreadMarker) + Send + 'static) {
    DispatchQueue::main().exec_async(move || {
        let mtm = MainThreadMarker::new().expect("the main queue runs on the main thread");
        work(mtm);
    });
}

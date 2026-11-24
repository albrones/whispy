//! V1's recording pill, ported from `src/whispy/ui/waveform_window.py`: a
//! non-activating panel at the bottom centre of the main screen, hosting a
//! custom view that draws a rounded dark background and 11 level-reactive bars,
//! repainted at 30 fps by a timer that also fades the panel in and out.
//!
//! The geometry, colours and easing are the pure functions of
//! `pill_geometry`; this file only does AppKit. All AppKit objects and the
//! animation state live on the main thread; [`PillFeedback`] is a zero-size
//! `Send` handle whose methods hop to the main queue, as `menu_bar::show` does.
//!
//! A type-while-speaking recording also carries a caption: the first non-empty
//! one widens the panel and adds a row below the bars (the panel extends downward,
//! so the bars stay put and centred) and `drawRect:` paints one attributed line
//! there, centred and truncated at its head so the latest words stay visible. Drawing it ourselves keeps the pill what it was, a panel that ignores
//! the mouse and never takes focus: no text field, nothing selectable or editable.

use std::cell::{Cell, RefCell};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Instant;

use dispatch2::DispatchQueue;
use objc2::rc::Retained;
use objc2::runtime::AnyObject;
use objc2::{define_class, msg_send, sel, MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{
    NSAttributedStringNSStringDrawing, NSBackingStoreType, NSBezierPath, NSColor, NSFont,
    NSFontAttributeName, NSForegroundColorAttributeName, NSLineBreakMode, NSMutableParagraphStyle,
    NSPanel, NSParagraphStyleAttributeName, NSScreen, NSScreenSaverWindowLevel, NSSound,
    NSTextAlignment, NSView, NSWindowCollectionBehavior, NSWindowStyleMask,
};
use objc2_foundation::{
    NSMutableAttributedString, NSObject, NSPoint, NSRange, NSRect, NSSize, NSString, NSTimer,
};

use super::notify;
use crate::feedback::{Caption, Feedback, Phase};
use crate::log;
use crate::menu_model::Alert;
use crate::pill_geometry::{
    advance_phase, bar_color, bar_heights, bar_rects, caption_text_rect, fade_step, level_from_rms,
    pill_frame, pill_size, smooth, Rect, BACKGROUND, BAR_WIDTH, CAPTION_COMMITTED_ALPHA,
    CAPTION_FONT_SIZE, CAPTION_PROVISIONAL_ALPHA, CORNER_RADIUS, FPS, HIDE_BELOW_ALPHA,
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
    /// A caption has shown in this recording: the panel is wide until the next one.
    captioned: bool,
}

thread_local! {
    static PILL: RefCell<Option<Pill>> = const { RefCell::new(None) };
    /// What `drawRect:` paints: (smoothed level, wobble phase). Separate from
    /// [`PILL`] so drawing never re-enters its borrow.
    static DRAW: Cell<(f64, f64)> = const { Cell::new((0.0, 0.0)) };
    /// The caption `drawRect:` paints, apart from [`PILL`] for the same reason.
    static CAPTION: RefCell<Caption> = RefCell::new(Caption::default());
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
            let pill = NSBezierPath::bezierPathWithRoundedRect_xRadius_yRadius(
                bounds,
                CORNER_RADIUS,
                CORNER_RADIUS,
            );
            srgb(BACKGROUND).set();
            pill.fill();

            // Bars, centred horizontally, in the top 52 pt (all of it without a caption).
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

            CAPTION.with(|caption| draw_caption(&caption.borrow(), width));
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

/// One line of text in the row below the bars, centred: committed words bright, provisional ones
/// faded, the head cut with an ellipsis when it does not fit.
fn draw_caption(caption: &Caption, width: f64) {
    let committed = caption.committed.trim();
    let provisional = caption.provisional.trim();
    let text = match (committed.is_empty(), provisional.is_empty()) {
        (true, true) => return,
        (false, false) => format!("{committed} {provisional}"),
        (false, true) => committed.to_owned(),
        (true, false) => provisional.to_owned(),
    };
    // Ranges are in UTF-16 units, as NSString counts them.
    let committed_len = committed.encode_utf16().count();
    let total_len = text.encode_utf16().count();

    let font = NSFont::systemFontOfSize(CAPTION_FONT_SIZE);
    let style = NSMutableParagraphStyle::new();
    style.setAlignment(NSTextAlignment::Center);
    style.setLineBreakMode(NSLineBreakMode::ByTruncatingHead);
    let faded = srgb((1.0, 1.0, 1.0, CAPTION_PROVISIONAL_ALPHA));
    let bright = srgb((1.0, 1.0, 1.0, CAPTION_COMMITTED_ALPHA));

    let string = NSMutableAttributedString::from_nsstring(&NSString::from_str(&text));
    let whole = NSRange::new(0, total_len);
    // SAFETY: the keys are AppKit's attribute names and each value is the object type it expects.
    unsafe {
        string.addAttribute_value_range(NSFontAttributeName, &font, whole);
        string.addAttribute_value_range(NSParagraphStyleAttributeName, &style, whole);
        string.addAttribute_value_range(NSForegroundColorAttributeName, &faded, whole);
        string.addAttribute_value_range(
            NSForegroundColorAttributeName,
            &bright,
            NSRange::new(0, committed_len),
        );
    }
    string.drawInRect(rect(caption_text_rect(width)));
}

fn srgb((r, g, b, a): (f64, f64, f64, f64)) -> Retained<NSColor> {
    NSColor::colorWithSRGBRed_green_blue_alpha(r, g, b, a)
}

fn rect((x, y, w, h): Rect) -> NSRect {
    NSRect::new(NSPoint::new(x, y), NSSize::new(w, h))
}

impl Pill {
    fn build(mtm: MainThreadMarker) -> Pill {
        let (width, height) = pill_size(false);
        let frame = rect((0.0, 0.0, width, height));
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
            captioned: false,
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

        // A new recording starts without a caption, at V1's size.
        self.captioned = false;
        CAPTION.with(|caption| *caption.borrow_mut() = Caption::default());
        if !self.place(mtm) {
            return;
        }

        // Start transparent and fade in through the timer.
        self.panel.setAlphaValue(0.0);
        self.fade_target = 1.0;
        self.panel.orderFrontRegardless();
        self.start_animation();
    }

    /// Sizes the panel for the current size and puts it bottom-centre of the active
    /// screen (the first one if there is no main one). False when there is no screen.
    fn place(&mut self, mtm: MainThreadMarker) -> bool {
        let screen = NSScreen::mainScreen(mtm).or_else(|| NSScreen::screens(mtm).firstObject());
        let Some(screen) = screen else {
            log::line("pill: no screen available");
            return false;
        };
        let visible = screen.visibleFrame();
        let frame = pill_frame(
            (
                visible.origin.x,
                visible.origin.y,
                visible.size.width,
                visible.size.height,
            ),
            self.captioned,
        );
        self.panel.setFrame_display(rect(frame), false);
        true
    }

    /// Shows the words heard. The first non-empty caption of a recording grows the
    /// panel, which then keeps that size until the next recording, so the line does
    /// not jitter. A caption that arrives after the pill started fading out is stale.
    fn set_caption(&mut self, mtm: MainThreadMarker, caption: Caption) {
        if self.fade_target == 0.0 {
            return;
        }
        let empty = caption.committed.trim().is_empty() && caption.provisional.trim().is_empty();
        if !self.captioned && !empty {
            self.captioned = true;
            self.place(mtm);
        }
        CAPTION.with(|cell| *cell.borrow_mut() = caption);
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

    fn caption(&mut self, caption: &Caption) {
        let caption = caption.clone();
        on_main(move |mtm| {
            PILL.with(|cell| {
                if let Some(pill) = cell.borrow_mut().as_mut() {
                    pill.set_caption(mtm, caption);
                }
            })
        });
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

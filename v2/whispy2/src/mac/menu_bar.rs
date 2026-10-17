//! The menu bar icon and its menu: what V2 is doing, and Quit.
//!
//! AppKit objects live on the main thread only; [`show`] may be called from
//! any thread and hops to the main queue.

use std::cell::{OnceCell, RefCell};

use dispatch2::DispatchQueue;
use objc2::rc::Retained;
use objc2::runtime::AnyObject;
use objc2::{define_class, msg_send, sel, MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{
    NSApplication, NSImage, NSMenu, NSMenuItem, NSStatusBar, NSStatusItem,
    NSVariableStatusItemLength,
};
use objc2_foundation::{NSObject, NSString};

use crate::controller::Status;
use crate::machine::State;

struct MenuBar {
    item: Retained<NSStatusItem>,
    headline: Retained<NSMenuItem>,
    note: Retained<NSMenuItem>,
    /// The Quit item's target; a menu item does not retain its target.
    _quit_target: Retained<QuitTarget>,
}

thread_local! {
    static MENU_BAR: OnceCell<MenuBar> = const { OnceCell::new() };
    static ON_QUIT: RefCell<Option<Box<dyn FnOnce()>>> = const { RefCell::new(None) };
}

define_class!(
    // SAFETY: NSObject has no subclassing requirements; QuitTarget adds no ivars.
    #[unsafe(super(NSObject))]
    #[thread_kind = MainThreadOnly]
    #[name = "Whispy2QuitTarget"]
    struct QuitTarget;

    impl QuitTarget {
        // SAFETY: the signature matches an AppKit action, `- (void)quit:(id)sender`.
        #[unsafe(method(quit:))]
        fn quit(&self, _sender: Option<&AnyObject>) {
            // Runs the shutdown before `terminate:` calls `exit`.
            if let Some(shutdown) = ON_QUIT.with(|cell| cell.borrow_mut().take()) {
                shutdown();
            }
            NSApplication::sharedApplication(self.mtm()).terminate(None);
        }
    }
);

/// Puts the icon in the menu bar. Call once, on the main thread, before
/// [`show`]. `on_quit` runs on Quit, before the process exits.
pub fn install(mtm: MainThreadMarker, on_quit: impl FnOnce() + 'static) {
    ON_QUIT.with(|cell| *cell.borrow_mut() = Some(Box::new(on_quit)));
    let item = NSStatusBar::systemStatusBar().statusItemWithLength(NSVariableStatusItemLength);
    let menu = NSMenu::new(mtm);
    let headline = text_line(mtm, "Starting…");
    let note = text_line(mtm, "");
    note.setHidden(true);
    menu.addItem(&headline);
    menu.addItem(&note);
    menu.addItem(&NSMenuItem::separatorItem(mtm));
    // SAFETY: plain allocation and `init` of an NSObject subclass.
    let quit_target: Retained<QuitTarget> = unsafe { msg_send![QuitTarget::alloc(mtm), init] };
    // SAFETY: `quit:` is implemented by QuitTarget, which `MenuBar` keeps alive.
    let quit = unsafe {
        let quit = NSMenuItem::initWithTitle_action_keyEquivalent(
            NSMenuItem::alloc(mtm),
            &NSString::from_str("Quit Whispy V2"),
            Some(sel!(quit:)),
            &NSString::from_str("q"),
        );
        quit.setTarget(Some(&quit_target));
        quit
    };
    menu.addItem(&quit);
    item.setMenu(Some(&menu));
    let menu_bar = MenuBar {
        item,
        headline,
        note,
        _quit_target: quit_target,
    };
    menu_bar.set_icon(mtm, State::Idle);
    MENU_BAR.with(|cell| {
        if cell.set(menu_bar).is_err() {
            panic!("menu_bar::install called twice");
        }
    });
}

/// Shows `status` in the menu bar, from any thread.
pub fn show(status: Status) {
    DispatchQueue::main().exec_async(move || {
        let mtm = MainThreadMarker::new().expect("the main queue runs on the main thread");
        MENU_BAR.with(|cell| {
            if let Some(menu_bar) = cell.get() {
                menu_bar.show(mtm, &status);
            }
        });
    });
}

impl MenuBar {
    fn show(&self, mtm: MainThreadMarker, status: &Status) {
        self.set_icon(mtm, status.state);
        self.headline
            .setTitle(&NSString::from_str(status.headline()));
        match &status.note {
            Some(note) => {
                self.note.setTitle(&NSString::from_str(note));
                self.note.setHidden(false);
            }
            None => self.note.setHidden(true),
        }
    }

    fn set_icon(&self, mtm: MainThreadMarker, state: State) {
        let (symbol, description) = match state {
            State::Idle => ("mic", "Whispy V2: ready"),
            State::Recording { .. } => ("mic.fill", "Whispy V2: recording"),
            State::Transcribing { .. } | State::Inserting => {
                ("ellipsis.circle", "Whispy V2: transcribing")
            }
            State::Yielded => ("mic.slash", "Whispy V2: paused while V1 runs"),
        };
        let Some(button) = self.item.button(mtm) else {
            return;
        };
        match NSImage::imageWithSystemSymbolName_accessibilityDescription(
            &NSString::from_str(symbol),
            Some(&NSString::from_str(description)),
        ) {
            Some(image) => {
                image.setTemplate(true);
                button.setImage(Some(&image));
            }
            // SF Symbols exist from macOS 11; older systems get text.
            None => button.setTitle(&NSString::from_str("W2")),
        }
    }
}

/// A menu line that only shows text: no action, so the menu draws it disabled.
fn text_line(mtm: MainThreadMarker, title: &str) -> Retained<NSMenuItem> {
    // SAFETY: no action selector, nothing to dispatch.
    unsafe {
        NSMenuItem::initWithTitle_action_keyEquivalent(
            NSMenuItem::alloc(mtm),
            &NSString::from_str(title),
            None,
            &NSString::from_str(""),
        )
    }
}

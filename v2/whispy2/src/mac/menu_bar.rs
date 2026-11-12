//! The menu bar title and menu, V1's look: the braille waveform as the title,
//! and the menu `menu_model::build` describes, rendered as `NSMenuItem`s.
//!
//! AppKit objects live on the main thread only; [`show`] and
//! [`set_trigger_down`] may be called from any thread.

use std::cell::{OnceCell, RefCell};
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::Arc;

use dispatch2::DispatchQueue;
use objc2::rc::Retained;
use objc2::runtime::AnyObject;
use objc2::{define_class, msg_send, sel, AnyThread, MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{
    NSApplication, NSColor, NSForegroundColorAttributeName, NSKernAttributeName, NSMenu,
    NSMenuItem, NSStatusBar, NSStatusItem, NSVariableStatusItemLength,
};
use objc2_foundation::{
    NSArray, NSBundle, NSMutableAttributedString, NSNumber, NSObject, NSRange, NSRunLoop,
    NSRunLoopCommonModes, NSString, NSTimer,
};

use super::login_item::{self, LoginState};
use super::trigger_tap::TriggerKeyHandle;
use crate::controller::{Input, Source, Status, LOADING_NOTE};
use crate::log;
use crate::machine::{Event, State};
use crate::menu_logic::{self, Relaunch};
use crate::menu_model::{
    self, LoginRow, MenuAction, MenuInput, MenuRow, Pane, RowKind, StatusFacts,
};
use crate::settings::{self, Settings};
use crate::theme::{self, Title};
use crate::title_anim;

/// What the menu needs to act on a choice. Built on the main thread.
pub struct Handles {
    /// The effective settings; the menu is the only writer after startup.
    pub settings: Rc<RefCell<Settings>>,
    pub settings_path: Option<PathBuf>,
    /// Typed delivery (copy to clipboard off), shared with the inserter.
    pub typed: Arc<AtomicBool>,
    /// The tap's trigger keycode; `None` when the tap could not be installed.
    pub trigger_key: Option<TriggerKeyHandle>,
    pub inputs: Sender<Input>,
    /// The control socket, which a restart waits to see freed.
    pub socket: Option<PathBuf>,
}

/// What the last rendering was built from; an identical rebuild is skipped so
/// an open menu is not disturbed by every status push.
#[derive(PartialEq)]
struct Rendered {
    rows: Vec<MenuRow>,
    note: Option<String>,
    dark: bool,
}

struct Inner {
    status: Status,
    /// A message of the menu's own (a settings save that failed, a login failure).
    note: Option<String>,
    dark: bool,
    rendered: Option<Rendered>,
    frame: usize,
    shown_title: String,
    was_trigger_down: bool,
}

struct MenuBar {
    item: Retained<NSStatusItem>,
    menu: Retained<NSMenu>,
    /// The action target, menu delegate and timer target; AppKit holds it weakly.
    target: Retained<MenuTarget>,
    handles: Handles,
    inner: RefCell<Inner>,
    mtm: MainThreadMarker,
    /// Kept so the timer lives as long as the bar.
    _timer: Retained<NSTimer>,
}

thread_local! {
    static MENU_BAR: OnceCell<MenuBar> = const { OnceCell::new() };
    static ON_QUIT: RefCell<Option<Box<dyn FnOnce()>>> = const { RefCell::new(None) };
}

/// The trigger key is held, as the tap callback saw it last ("Listening…").
static TRIGGER_DOWN: AtomicBool = AtomicBool::new(false);

/// Reports the trigger key's state, from the tap callback. The next animation
/// tick (90 ms) picks it up.
pub fn set_trigger_down(down: bool) {
    TRIGGER_DOWN.store(down, Ordering::SeqCst);
}

define_class!(
    // SAFETY: NSObject has no subclassing requirements; MenuTarget adds no ivars.
    #[unsafe(super(NSObject))]
    #[thread_kind = MainThreadOnly]
    #[name = "Whispy2MenuTarget"]
    struct MenuTarget;

    impl MenuTarget {
        // SAFETY: the signature matches an AppKit action, `- (void)choose:(id)sender`.
        #[unsafe(method(choose:))]
        fn choose(&self, sender: &NSMenuItem) {
            if let Some(action) = menu_logic::tag_action(sender.tag()) {
                with_menu_bar(|menu_bar| menu_bar.perform(action));
            }
        }

        // SAFETY: the signature matches `NSMenuDelegate`'s `- (void)menuWillOpen:(NSMenu *)menu`.
        #[unsafe(method(menuWillOpen:))]
        fn menu_will_open(&self, _menu: &NSMenu) {
            // The login item may have changed in System Settings, the appearance too.
            with_menu_bar(|menu_bar| menu_bar.rebuild());
        }

        // SAFETY: the signature matches an NSTimer selector, `- (void)tick:(NSTimer *)timer`.
        #[unsafe(method(tick:))]
        fn tick(&self, _timer: &NSTimer) {
            with_menu_bar(|menu_bar| menu_bar.tick());
        }
    }
);

fn with_menu_bar(run: impl FnOnce(&MenuBar)) {
    MENU_BAR.with(|cell| {
        if let Some(menu_bar) = cell.get() {
            run(menu_bar);
        }
    });
}

/// Puts the icon in the menu bar. Call once, on the main thread. `on_quit`
/// runs on Quit and Restart, before the process exits.
pub fn install(mtm: MainThreadMarker, handles: Handles, on_quit: impl FnOnce() + 'static) {
    ON_QUIT.with(|cell| *cell.borrow_mut() = Some(Box::new(on_quit)));
    let item = NSStatusBar::systemStatusBar().statusItemWithLength(NSVariableStatusItemLength);
    let menu = NSMenu::new(mtm);
    // `autoenablesItems` would re-enable the disabled rows (they have a target).
    menu.setAutoenablesItems(false);
    // SAFETY: plain allocation and `init` of an NSObject subclass.
    let target: Retained<MenuTarget> = unsafe { msg_send![MenuTarget::alloc(mtm), init] };
    // SAFETY: MenuTarget implements `menuWillOpen:`, the only delegate method used.
    unsafe {
        let delegate: &AnyObject = &target;
        let _: () = msg_send![&*menu, setDelegate: delegate];
    }
    item.setMenu(Some(&menu));
    if let Some(button) = item.button(mtm) {
        // V1's title is the waveform text, not an icon.
        button.setImage(None);
    }

    // Common modes, so the waveform keeps scrolling while the menu is open
    // (V1's rumps timer runs in the default mode only and stops then).
    let target_object: &AnyObject = &target;
    // SAFETY: `tick:` is implemented by MenuTarget, which the timer retains.
    let timer = unsafe {
        let timer = NSTimer::timerWithTimeInterval_target_selector_userInfo_repeats(
            title_anim::INTERVAL.as_secs_f64(),
            target_object,
            sel!(tick:),
            None,
            true,
        );
        NSRunLoop::mainRunLoop().addTimer_forMode(&timer, NSRunLoopCommonModes);
        timer
    };

    let status = Status {
        state: State::Idle,
        note: Some(LOADING_NOTE.into()),
        models_loaded: false,
        trigger_mode: handles.settings.borrow().trigger_mode,
        permission_pane: None,
    };
    let menu_bar = MenuBar {
        item,
        menu,
        target,
        handles,
        inner: RefCell::new(Inner {
            status,
            note: None,
            dark: false,
            rendered: None,
            frame: 0,
            shown_title: String::new(),
            was_trigger_down: false,
        }),
        mtm,
        _timer: timer,
    };
    menu_bar.tick();
    menu_bar.rebuild();
    MENU_BAR.with(|cell| {
        if cell.set(menu_bar).is_err() {
            panic!("menu_bar::install called twice");
        }
    });
}

/// Shows `status` in the menu bar, from any thread.
pub fn show(status: Status) {
    DispatchQueue::main().exec_async(move || {
        with_menu_bar(|menu_bar| {
            menu_bar.inner.borrow_mut().status = status;
            menu_bar.tick();
            menu_bar.rebuild();
        });
    });
}

/// Whether the app's effective appearance is Dark Aqua (best match of Aqua, DarkAqua).
fn is_dark(mtm: MainThreadMarker) -> bool {
    let app = NSApplication::sharedApplication(mtm);
    // SAFETY: `effectiveAppearance` returns an NSAppearance; `bestMatchFromAppearancesWithNames:`
    // takes an array of appearance names and returns one of them or nil.
    unsafe {
        let appearance: Retained<AnyObject> = msg_send![&*app, effectiveAppearance];
        let aqua = NSString::from_str("NSAppearanceNameAqua");
        let dark = NSString::from_str("NSAppearanceNameDarkAqua");
        let names = NSArray::from_slice(&[&*aqua, &*dark]);
        let best: Option<Retained<NSString>> =
            msg_send![&*appearance, bestMatchFromAppearancesWithNames: &*names];
        best.is_some_and(|name| name.to_string() == "NSAppearanceNameDarkAqua")
    }
}

fn pane_of(status: &Status) -> Option<Pane> {
    status.permission_pane
}

impl MenuBar {
    /// One animation step: the title frame, and a menu rebuild when what the
    /// menu shows changed under it (appearance, trigger key).
    fn tick(&self) {
        let trigger_down = TRIGGER_DOWN.load(Ordering::SeqCst);
        let dark = is_dark(self.mtm);
        let mut inner = self.inner.borrow_mut();
        let active = menu_logic::is_active(&inner.status, trigger_down);
        if active {
            inner.frame = inner.frame.wrapping_add(1);
        } else {
            inner.frame = 0;
        }
        let frame = title_anim::select_frame(inner.frame, active);
        if inner.shown_title != frame {
            if let Some(button) = self.item.button(self.mtm) {
                button.setTitle(&NSString::from_str(frame));
            }
            inner.shown_title = frame.to_string();
        }
        let flipped = dark != inner.dark || trigger_down != inner.was_trigger_down;
        inner.was_trigger_down = trigger_down;
        drop(inner);
        if flipped {
            self.rebuild();
        }
    }

    fn login_row(&self) -> LoginRow {
        if !login_item::is_available() {
            return LoginRow::Hidden;
        }
        match login_item::state() {
            LoginState::Enabled => LoginRow::On,
            LoginState::RequiresApproval => LoginRow::NeedsApproval,
            LoginState::NotRegistered | LoginState::NotFound => LoginRow::Off,
        }
    }

    /// Rebuilds the menu from the current facts, unless nothing changed.
    fn rebuild(&self) {
        let dark = is_dark(self.mtm);
        let (rows, note) = {
            let mut inner = self.inner.borrow_mut();
            inner.dark = dark;
            let settings = self.handles.settings.borrow();
            let facts: StatusFacts =
                menu_logic::status_facts(&inner.status, TRIGGER_DOWN.load(Ordering::SeqCst));
            let input = MenuInput {
                status_text: menu_model::status_text(&facts).to_string(),
                copy_to_clipboard: settings.copy_to_clipboard,
                toggle_mode: settings.trigger_mode == settings::TriggerMode::Toggle,
                trigger_keycode: settings.trigger.keycode,
                trigger_label: menu_model::trigger_label(settings.trigger.keycode),
                login: self.login_row(),
                permission_warning: pane_of(&inner.status).is_some(),
                dark,
            };
            let note = inner
                .note
                .clone()
                .or_else(|| inner.status.last_problem().map(str::to_string));
            (menu_model::build(&input), note)
        };
        let rendered = Rendered { rows, note, dark };
        if self.inner.borrow().rendered.as_ref() == Some(&rendered) {
            return;
        }
        self.menu.removeAllItems();
        let accent = {
            let (r, g, b) = theme::accent(dark);
            NSColor::colorWithSRGBRed_green_blue_alpha(
                f64::from(r) / 255.0,
                f64::from(g) / 255.0,
                f64::from(b) / 255.0,
                1.0,
            )
        };
        for row in &rendered.rows {
            self.menu.addItem(&self.render(row, &accent));
            if matches!(row.kind, RowKind::Status) {
                if let Some(note) = &rendered.note {
                    let item = self.item_with(&Title::plain(note.as_str()), &accent);
                    item.setEnabled(false);
                    self.menu.addItem(&item);
                }
            }
        }
        self.inner.borrow_mut().rendered = Some(rendered);
    }

    fn item_with(&self, title: &Title, accent: &NSColor) -> Retained<NSMenuItem> {
        // SAFETY: no action selector: nothing to dispatch.
        let item = unsafe {
            NSMenuItem::initWithTitle_action_keyEquivalent(
                NSMenuItem::alloc(self.mtm),
                &NSString::from_str(&title.text),
                None,
                &NSString::from_str(""),
            )
        };
        if !title.accents.is_empty() || title.kern.is_some() {
            item.setAttributedTitle(Some(&attributed(title, accent)));
        }
        item
    }

    fn render(&self, row: &MenuRow, accent: &NSColor) -> Retained<NSMenuItem> {
        if matches!(row.kind, RowKind::Separator) {
            return NSMenuItem::separatorItem(self.mtm);
        }
        let item = self.item_with(&row.title, accent);
        item.setEnabled(row.enabled);
        match &row.kind {
            RowKind::PermissionWarning { visible } => {
                self.wire(&item, MenuAction::OpenPermissionSettings);
                item.setHidden(!visible);
            }
            RowKind::Toggle { action, .. }
            | RowKind::Choice { action, .. }
            | RowKind::Action { action, .. } => {
                if row.enabled {
                    self.wire(&item, *action);
                }
                if let RowKind::Action {
                    key_equivalent: Some(key),
                    ..
                } = &row.kind
                {
                    item.setKeyEquivalent(&NSString::from_str(key));
                }
            }
            RowKind::Submenu { items } => {
                let submenu = NSMenu::new(self.mtm);
                submenu.setAutoenablesItems(false);
                for choice in items {
                    submenu.addItem(&self.render(choice, accent));
                }
                item.setSubmenu(Some(&submenu));
            }
            RowKind::Header | RowKind::Status | RowKind::Section | RowKind::Separator => {}
        }
        item
    }

    fn wire(&self, item: &NSMenuItem, action: MenuAction) {
        item.setTag(menu_logic::action_tag(action));
        let target: &AnyObject = &self.target;
        // SAFETY: `choose:` is implemented by MenuTarget, which `MenuBar` keeps alive.
        unsafe {
            item.setAction(Some(sel!(choose:)));
            item.setTarget(Some(target));
        }
    }

    fn perform(&self, action: MenuAction) {
        match action {
            MenuAction::ToggleCopy | MenuAction::ToggleMode | MenuAction::SelectTrigger(_) => {
                self.change_setting(action);
            }
            MenuAction::ToggleLogin => {
                let failure = login_item::toggle().err();
                let approval = (login_item::is_available()
                    && login_item::state() == LoginState::RequiresApproval)
                    .then(|| login_item::APPROVAL_NOTE.to_string());
                self.inner.borrow_mut().note = failure.or(approval);
            }
            MenuAction::OpenPermissionSettings => {
                if let Some(pane) = pane_of(&self.inner.borrow().status) {
                    let _ = Command::new("open")
                        .arg(menu_model::settings_url(pane))
                        .stdin(Stdio::null())
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .spawn();
                }
            }
            MenuAction::Restart => {
                self.spawn_restart();
                self.quit();
            }
            MenuAction::Quit => self.quit(),
        }
        self.rebuild();
    }

    /// Saves the change first; only a saved change is applied, so the menu
    /// never shows a setting the file does not hold.
    fn change_setting(&self, action: MenuAction) {
        let current = self.handles.settings.borrow().clone();
        let Some(change) = menu_logic::change_for(action, &current) else {
            return;
        };
        let saved = match &self.handles.settings_path {
            Some(path) => settings::save_key(path, change.key(), change.value()),
            None => Err("the settings path is unknown (no HOME)".to_string()),
        };
        if let Err(error) = saved {
            log::line(&format!("could not save {}: {error}", change.key()));
            self.inner.borrow_mut().note = Some(format!("Could not save the setting: {error}"));
            return;
        }
        change.apply(&mut self.handles.settings.borrow_mut());
        match &change {
            menu_logic::Change::Copy(copy) => self.handles.typed.store(!copy, Ordering::SeqCst),
            menu_logic::Change::Mode(mode) => {
                let _ = self
                    .handles
                    .inputs
                    .send(Input::Event(Event::Settings(*mode), Source::Fn));
            }
            menu_logic::Change::Trigger(trigger) => {
                if let Some(key) = &self.handles.trigger_key {
                    key.set(trigger.keycode);
                }
            }
        }
        self.inner.borrow_mut().note = None;
    }

    /// A detached waiter that starts the new instance once this one has freed the socket.
    fn spawn_restart(&self) {
        let bundle = login_item::is_available()
            .then(|| PathBuf::from(NSBundle::mainBundle().bundlePath().to_string()));
        let executable = std::env::current_exe().ok();
        let target = match (&bundle, &executable) {
            (Some(bundle), _) => Relaunch::Bundle(bundle),
            (None, Some(executable)) => Relaunch::Executable(executable),
            (None, None) => {
                log::line("restart: the executable path is unknown; only quitting");
                return;
            }
        };
        let args = menu_logic::restart_command(self.handles.socket.as_deref(), target);
        let spawned = Command::new("/bin/sh")
            .args(&args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            // Its own process group: it outlives this process.
            .process_group(0)
            .spawn();
        if let Err(error) = spawned {
            log::line(&format!("restart: could not start the waiter: {error}"));
        }
    }

    /// The normal Quit path: free the models and the socket, then terminate.
    fn quit(&self) {
        if let Some(shutdown) = ON_QUIT.with(|cell| cell.borrow_mut().take()) {
            shutdown();
        }
        NSApplication::sharedApplication(self.mtm).terminate(None);
    }
}

/// `title` as an attributed string: the accent colour over each accent range
/// (UTF-16, as `NSRange` counts) and the letter spacing over the whole text.
fn attributed(title: &Title, accent: &NSColor) -> Retained<NSMutableAttributedString> {
    let text = NSString::from_str(&title.text);
    let attributed =
        NSMutableAttributedString::initWithString(NSMutableAttributedString::alloc(), &text);
    // SAFETY: the foreground colour is an NSColor and the kern an NSNumber, the
    // value types AppKit documents for these keys; the ranges lie inside the text.
    unsafe {
        for &(start, length) in &title.accents {
            attributed.addAttribute_value_range(
                NSForegroundColorAttributeName,
                accent,
                NSRange::new(start, length),
            );
        }
        if let Some(kern) = title.kern {
            attributed.addAttribute_value_range(
                NSKernAttributeName,
                &NSNumber::new_f64(kern),
                NSRange::new(0, title.text.encode_utf16().count()),
            );
        }
    }
    attributed
}

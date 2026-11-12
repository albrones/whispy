//! V1's alerts as notifications: title "Whispy", the alert's subtitle, its
//! message as the body, through `UNUserNotificationCenter`.
//!
//! The center only exists for an app running from a bundle (asking for it
//! outside one raises an Objective-C exception), so everything here is a no-op
//! elsewhere. The posting call is asynchronous: it never blocks the controller
//! thread that calls [`post`].

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;

use block2::RcBlock;
use objc2::runtime::Bool;
use objc2_foundation::{NSError, NSString};
use objc2_user_notifications::{
    UNAuthorizationOptions, UNMutableNotificationContent, UNNotificationRequest,
    UNUserNotificationCenter,
};

use super::login_item;
use crate::log;
use crate::menu_model::Alert;

/// Whether notifications can work here: only inside a `.app` bundle. Logged once.
fn is_available() -> bool {
    static AVAILABLE: OnceLock<bool> = OnceLock::new();
    *AVAILABLE.get_or_init(|| {
        let available = login_item::is_available();
        if !available {
            log::line("notifications are off: not running from an app bundle");
        }
        available
    })
}

/// Asks for permission to show alerts and play sounds, once, at startup. The
/// system remembers the answer; a denial leaves alerts in the log and the menu.
pub fn request_authorization() {
    if !is_available() {
        return;
    }
    let center = UNUserNotificationCenter::currentNotificationCenter();
    let done = RcBlock::new(|granted: Bool, error: *mut NSError| {
        // SAFETY: the system passes a valid NSError or null.
        if let Some(error) = unsafe { error.as_ref() } {
            log::line(&format!(
                "notification authorization failed: {}",
                error.localizedDescription()
            ));
        } else if !granted.as_bool() {
            log::line("notifications are denied: alerts stay in the log and the menu");
        }
    });
    center.requestAuthorizationWithOptions_completionHandler(
        UNAuthorizationOptions::Alert | UNAuthorizationOptions::Sound,
        &done,
    );
}

/// Posts `alert` now. Any thread; returns at once.
pub fn post(alert: &Alert) {
    if !is_available() {
        return;
    }
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let content = UNMutableNotificationContent::new();
    content.setTitle(&NSString::from_str("Whispy"));
    content.setSubtitle(&NSString::from_str(&alert.subtitle));
    content.setBody(&NSString::from_str(&alert.message));
    let identifier = format!(
        "whispy2-{}-{}",
        log::unix_now(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    let request = UNNotificationRequest::requestWithIdentifier_content_trigger(
        &NSString::from_str(&identifier),
        &content,
        None,
    );
    let center = UNUserNotificationCenter::currentNotificationCenter();
    center.addNotificationRequest_withCompletionHandler(&request, None);
}

//! "Start at login": the OS login-item state of the V2 bundle, through
//! `SMAppService.mainApp`. The OS is the only record of the setting.

use std::path::Path;

use objc2_service_management::{SMAppService, SMAppServiceStatus};

/// The note shown when the OS wants the user's approval.
pub const APPROVAL_NOTE: &str = "Approve Whispy V2 in System Settings \u{2192} Login Items";

/// What the OS says about the login item.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LoginState {
    Enabled,
    NotRegistered,
    RequiresApproval,
    NotFound,
}

/// SMAppService only knows an app that runs from a bundle: the executable must
/// sit in `*.app/Contents/MacOS/`. A binary run from `v2/target` cannot be one.
pub fn login_item_available(executable: &Path) -> bool {
    let Some(macos) = executable.parent() else {
        return false;
    };
    let Some(contents) = macos.parent() else {
        return false;
    };
    let Some(app) = contents.parent() else {
        return false;
    };
    macos.file_name().is_some_and(|name| name == "MacOS")
        && contents.file_name().is_some_and(|name| name == "Contents")
        && app.extension().is_some_and(|extension| extension == "app")
}

/// Whether the running executable can be a login item.
pub fn is_available() -> bool {
    std::env::current_exe().is_ok_and(|path| login_item_available(&path))
}

pub fn state() -> LoginState {
    // SAFETY: plain class method returning the main app service.
    let status = unsafe { SMAppService::mainAppService().status() };
    if status == SMAppServiceStatus::Enabled {
        LoginState::Enabled
    } else if status == SMAppServiceStatus::RequiresApproval {
        LoginState::RequiresApproval
    } else if status == SMAppServiceStatus::NotFound {
        LoginState::NotFound
    } else {
        LoginState::NotRegistered
    }
}

/// Registers when it is off, unregisters when it is on. `Err` carries the note to show.
pub fn toggle() -> Result<LoginState, String> {
    // SAFETY: plain class method returning the main app service.
    let service = unsafe { SMAppService::mainAppService() };
    let enabled = matches!(state(), LoginState::Enabled | LoginState::RequiresApproval);
    // SAFETY: the service is valid; the call reports failure through the Result.
    let result = unsafe {
        if enabled {
            service.unregisterAndReturnError()
        } else {
            service.registerAndReturnError()
        }
    };
    if let Err(error) = result {
        return Err(format!(
            "Start at login failed: {}",
            error.localizedDescription()
        ));
    }
    Ok(state())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_bundle_executable_can_be_a_login_item() {
        assert!(login_item_available(Path::new(
            "/Applications/Whispy V2.app/Contents/MacOS/whispy2"
        )));
    }

    #[test]
    fn a_cargo_binary_cannot() {
        assert!(!login_item_available(Path::new(
            "/Users/me/whispy/v2/target/release/whispy2"
        )));
        assert!(!login_item_available(Path::new(
            "/Users/me/Foo.app/Contents/Resources/whispy2"
        )));
        assert!(!login_item_available(Path::new("whispy2")));
    }
}

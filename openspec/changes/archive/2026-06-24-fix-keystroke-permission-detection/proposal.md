## Why

After the rebrand to `com.whispy`, transcribed text stops appearing in text
fields even though the clipboard is correctly populated: the paste keystroke
(`tell System Events to keystroke "v"`) is denied with osascript error `1002`
("not authorized to send keystrokes"). macOS keys TCC grants to the bundle
identity, so the old Accessibility/Automation grant no longer applies to the
new bundle. The startup permission probe masks this — it reports "Automation
authorized" because it only runs a benign query (`return name`), which never
exercises the keystroke path that actually fails. Users get a silent failure
with no actionable signal.

## What Changes

- The startup permission probe SHALL detect when synthetic keystrokes are
  blocked, instead of passing on a benign query that does not need keystroke
  rights. A blocked keystroke must surface as a warning/notification with a
  remediation hint, not a false "authorized".
- Text injection SHALL detect the `1002` (errAEEventNotPermitted) failure at
  inject time and surface it to the user (log + user-visible notification) with
  the exact remediation, rather than failing silently into the clipboard.
- Add upgrade/migration guidance documenting the `tccutil reset` step required
  after the rebrand so the new bundle identity re-registers its grants.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `text-injection`: add a requirement that the injector detects a denied
  keystroke (osascript `1002`) and surfaces it with remediation, and that the
  startup permission check validates the keystroke path rather than a benign
  query.

## Impact

- Code: `src/whispy/platform/macos/permissions.py` (`ensure_automation_access`
  probe), `src/whispy/hardware/injection.py` (inject-time `1002` detection +
  notification), `src/whispy/ui/menu_bar.py` (user-visible alert hook).
- Docs: `README.md` / upgrade notes — `tccutil reset Accessibility com.whispy`
  and `tccutil reset AppleEvents com.whispy` after upgrading from the old name.
- No API or dependency changes. macOS-only behavior; Linux/X11 adapter
  unaffected.

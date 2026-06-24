## 1. Inject-time permission detection

- [x] 1.1 In `injection.py` `_spawn`, classify a non-zero exit whose stderr
      contains `(1002)` as a keystroke-permission denial (locale-independent —
      match the numeric code, not the localized message)
- [x] 1.2 On a detected denial, invoke a debounced callback (one notification
      per permission-state transition, not per utterance)
- [x] 1.3 Wire `TextInjector` to accept/expose a permission-denied callback so
      the engine/UI can subscribe

## 2. User-visible remediation

- [x] 2.1 In `menu_bar.py`, surface the denial via `rumps.notification` + a
      menu status line, with explicit remediation text (grant Accessibility +
      Automation, or `tccutil reset Accessibility com.whispy` /
      `tccutil reset AppleEvents com.whispy`, then restart)
- [x] 2.2 Subscribe the menu-bar handler to the injector's permission-denied
      callback in `engine.py` wiring

## 3. Honest startup probe

- [x] 3.1 In `permissions.py` `ensure_automation_access`, stop reporting
      "authorized" off a benign `return name` query; either probe the real
      keystroke path or downgrade the log to "keystroke authorization
      unverified" and defer to inject-time detection
- [x] 3.2 Ensure the probe matches on the `1002` code and emits the same
      remediation hint on failure

## 4. Tests

- [x] 4.1 unit-mocked: `subprocess` rc/stderr patched to emit `1002` →
      assert denial classified and callback fired (clipboard + keystroke modes)
- [x] 4.2 unit-mocked: debounce — repeated `1002` results trigger a single
      notification per state transition
- [x] 4.3 unit-mocked: startup probe — benign query passes but keystroke
      denied → not reported authorized; both pass → authorized

## 5. Docs

- [x] 5.1 Add upgrade/migration note to `README.md` documenting the
      `tccutil reset` step required after the rebrand to `com.whispy`

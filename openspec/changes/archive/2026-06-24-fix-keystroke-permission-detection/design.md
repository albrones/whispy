## Context

Text injection runs `osascript` telling Apple-signed `System Events` to type,
because Whispy is self/locally-signed and a direct `CGEventPost` is dropped.
Two macOS TCC grants gate this: Automation (Whispy → System Events Apple event)
and Accessibility (posting synthetic keystrokes, attributed to the controlling
app). Both are keyed to bundle identity (`com.whispy` + code signature).

After the rebrand the old grant no longer matches the new bundle, so the paste
keystroke is denied with `1002` (errAEEventNotPermitted) while clipboard write
— which needs no grant — still succeeds. The result is a silent failure.

The startup probe `ensure_automation_access()` runs `tell System Events to
return name`, a query that does **not** require keystroke rights, so it reports
"Automation authorized" even when keystrokes are blocked. Likewise
`AXIsProcessTrusted()` can return a stale/cached `true`. The probes don't
exercise the path that actually fails.

Observed log:
```
[INFO]    Accessibility already granted.
[INFO]    Automation (System Events) authorized.
[WARNING] [inject] osascript (clipboard) rc=1: ... osascript n'est pas
          autorisé à envoyer de saisies. (1002)
```

## Goals / Non-Goals

**Goals:**
- Detect a denied keystroke (`1002`) at inject time and surface it to the user
  with actionable remediation instead of failing silently.
- Make the startup probe validate the real keystroke path, so it never reports
  "authorized" when keystrokes are blocked.
- Document the `tccutil reset` upgrade step for the rebrand.

**Non-Goals:**
- Auto-granting or programmatically resetting TCC (impossible without user
  action / Full Disk Access).
- Changing the injection mechanism (osascript → System Events stays).
- Linux/X11 behavior — unchanged.

## Decisions

**1. Detect `1002` at inject time, not just startup.**
`_spawn` already captures `rc` and stderr off-thread. Add detection: when
`rc != 0` and stderr contains the `1002` error code, classify it as a
permission denial and trigger a user-visible notification (once, debounced, to
avoid spamming on every utterance). Inject-time detection is authoritative
because it observes the exact call that fails — startup probes can be stale.
*Alternative considered:* startup-only detection — rejected because
`AXIsProcessTrusted`/benign query both lie; only the live keystroke is truth.

**2. Replace the benign startup probe with a keystroke probe.**
`ensure_automation_access()` should attempt a harmless real keystroke against
System Events (e.g. a no-op modifier or a keystroke to a discardable target)
and inspect for `1002`, rather than `return name`. If a fully safe synthetic
keystroke probe proves intrusive, fall back to relying on inject-time
detection (Decision 1) and downgrade the startup line to "keystroke
authorization unverified" instead of a false "authorized".
*Alternative considered:* keep query-only probe — rejected, it is the source of
the false positive.

**3. Surface via the existing menu-bar UI.**
`menu_bar.py` (rumps) already owns user-facing status; route the notification
through it (`rumps.notification` + a menu state) so the message is visible
without the user reading `~/.whispy.log`. Debounce so repeated denials don't
flood Notification Center.

**4. Remediation text is explicit.**
The message names the concrete fix: grant Accessibility + Automation to Whispy,
or run `tccutil reset Accessibility com.whispy && tccutil reset AppleEvents
com.whispy`, then restart Whispy.

## Risks / Trade-offs

- A real keystroke startup probe could type a stray character into the focused
  app → mitigate by probing a key with no text effect, or skip the probe and
  rely on inject-time detection (Decision 1 is the safety net).
- Parsing osascript stderr for `1002` is locale-independent (the numeric code
  appears regardless of message language, as seen in the French log) → match on
  the `(1002)` code, not the localized text.
- Notification spam on repeated denials → debounce to one notification per
  permission-state transition.

## Migration Plan

1. Ship code changes (inject-time detection + probe + notification).
2. Document upgrade step: existing users run
   `tccutil reset Accessibility com.whispy` and
   `tccutil reset AppleEvents com.whispy`, relaunch, accept re-prompts.
3. No rollback concern — changes are additive (detection + messaging only).

## Open Questions

- Is there a synthetic keystroke that is guaranteed side-effect-free for the
  startup probe, or do we rely solely on inject-time detection? Lean toward
  inject-time detection as the source of truth and keep the startup line honest.

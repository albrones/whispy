## Context

The rebrand and release-install work landed a working install path, but a
follow-up security/UX review of the resulting code found several first-run
and privacy gaps that don't block the happy path but do erode trust or leak
data: silent permission/model failures, world-readable temp WAVs that
outlive their purpose, a clobbered clipboard, stale operational guidance
from the pre-rebrand LaunchAgent era, and a French-first default for a
tool now marketed internationally. This change closes those gaps in two
commits already on `feat/rebrand`: `d1a2c3a` (permission/model-load
visibility) and `8fe8e78` (privacy + UX + default-language fixes).

## Goals / Non-Goals

**Goals:**
- No first-run failure (permission denial, model-load failure, dictating
  before the model is ready) is silent — each surfaces a notification.
- No recorded voice audio outlives the transcription attempt that produced
  it, and while it exists on disk it is owner-only.
- Clipboard-mode injection never destroys the user's prior clipboard
  content.
- Operational guidance (event-tap errors, uninstall) reflects the current
  `.app`-bundle architecture, not the pre-rebrand LaunchAgent script.
- The shipped default language serves the v1 international audience.

**Non-Goals:**
- Redesigning the permission-request flow or adding new TCC entitlements —
  the four probes (mic, Input Monitoring, Accessibility, Automation)
  already existed; this only makes their result actionable.
- Windows support (out of scope for the whole project at this stage).
- Full model-download retry/resume logic — the model-load-failure alert
  tells the user to check their connection and use Restart, it doesn't
  automate a retry.

## Decisions

### Tri-state permission probes (`True` / `False` / `None`)
Each probe previously returned `None` unconditionally. Collapsing "granted",
"explicitly denied", and "undetermined" into one falsy-ish value made it
impossible for a caller to know whether to warn the user. `True` granted /
`False` explicit denial / `None` undetermined lets `Engine.start()` warn
only on `False` — an undetermined result means the system's own TCC prompt
is on screen, and warning there would be noise, not signal, on top of the
OS prompt.

### `on_permission_missing(kind, message)` as a new engine callback, not a rider on `on_model_load_failed`
Permission denials and model-load failures are different failure classes
with different remediation UI (open a specific System Settings pane vs.
"check your connection and Restart"). A single callback would force the
menu bar to string-match or otherwise infer which case it's in. Two
callbacks keep each side's contract simple: `on_permission_missing` carries
a `kind` (`"microphone" | "input_monitoring" | "accessibility" |
"automation"`) the menu bar maps directly to a `x-apple.systempreferences:`
deep link.

### Menu bar alert queue (`_pending_alerts`)
Engine callbacks (`on_permission_missing`, `on_model_load_failed`,
`_on_injection_denied`) all fire from worker threads (transcription,
injection, startup). AppKit calls (`rumps.notification`, menu item
mutation) must happen on the main thread. Rather than one single-slot
`_pending_perm_message` (the pre-existing pattern, which only handled one
alert class), alerts are queued as `(subtitle, message, settings_url)`
tuples and drained on the existing `_tick_anim` main-thread timer —
`settings_url` is `None` for non-permission alerts (model-load failure,
model-still-loading), which tells `_show_alert` to skip revealing the
warning menu item and only post the notification.

### WAV cleanup via `finally`, not per-branch
`run_transcription` previously called `cleanup_audio_file` only on the
success path (non-empty `text`). Model-not-loaded and exception paths left
the WAV behind. Moving the whole transcribe-and-inject body into a
`try/finally` guarantees cleanup regardless of how the function exits,
without duplicating the cleanup call at every return point.

### WAV permissions via `os.open` before `wave.open`
`wave.open(path, "wb")` has no mode parameter — it creates the file under
the process umask, which is `0o644` (world-readable) on a typical Linux
system. `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` sets the mode
atomically at creation; since the OS ignores the `mode` argument on an
already-existing file, the subsequent `wave.open` (which just reopens the
now-existing file) never widens the permissions back. This closes the
window without touching the WAV-writing logic itself.

### Stale-recording sweep is best-effort and startup-scoped
A crash (or, before the `finally` fix, an exception during transcription)
could leave a `whispy-<uuid>.wav` behind indefinitely. Sweeping at
`AudioEngine.__init__` (once per daemon start) is simple and catches the
common case (a computer restart or app relaunch after a crash) without
adding a background timer. The sweep is wrapped in its own `try/except`
so a `glob`/`remove` failure never prevents the daemon from starting.

### Clipboard snapshot/restore is plain-text only
The clipboard is snapshotted via `pbpaste` (stdout bytes) and restored via
`pbcopy` after a fixed 0.15 s delay (giving the target app time to read the
pasted transcript before the restore overwrites it again). This round-trips
plain text only — if the clipboard held rich text, an image, or a file
reference before dictation, only its plain-text form (or nothing) comes
back. Recovering the original data exactly would require capturing every
pasteboard type, which is a materially bigger change for a rare case
(dictating right after copying a non-text item); the plain-text round-trip
covers the common case (the user had text or nothing copied) and is
flagged as a known limitation rather than solved fully here.

If the paste step itself fails (e.g. `1002` keystroke-permission denial),
`_spawn` stops the step sequence before the restore step runs, deliberately
leaving the transcript on the clipboard — that's the existing documented
manual-paste fallback, and clobbering it with the restore would remove the
user's only way to recover the dictation.

### Default language: code default flips, persisted config does not
`DEFAULT_CONFIG["language"]` changes from `"fr"` to `"en"`. `load_config`
only substitutes a default for a key that is absent from the saved config
file (or when the file itself doesn't exist), so an existing install with
`"language": "fr"` already written to `~/.config/whispy/config.json` keeps
using French — no migration step needed, no silent language switch for
current users.

### Uninstall data removal defaults to "keep", is TTY-gated
Deleting the faster-whisper model cache means a reinstall re-downloads
0.5–3 GB. Defaulting the prompt to "N" avoids surprising data loss on a
routine uninstall/reinstall cycle. The prompt only runs when stdin is a TTY
(`[ -t 0 ]`); a non-interactive run (`bootstrap.sh` piped via `curl | bash`,
or the uninstall invoked from a script) always keeps the data rather than
blocking on an unanswerable `read`. The model-cache deletion is scoped to
the `models--Systran--faster-whisper-*` glob inside
`~/.cache/huggingface/hub` — that directory is shared with any other tool
using `huggingface_hub`, so deleting the whole hub cache would be
collateral damage to unrelated projects.

## Risks / Trade-offs

- The clipboard restore is plain-text only (see above) — a known, accepted
  gap rather than a full pasteboard-type round-trip.
- The 0.15 s clipboard-restore delay is a fixed heuristic, not a
  confirmation that the target app actually read the pasted content; a
  very slow app could theoretically still see the restored (old) clipboard
  if it reads asynchronously after the delay. This mirrors the existing
  paste-then-continue pattern and was not observed to regress in testing.
- Sweeping `whispy-*.wav` at every `AudioEngine` startup means a
  legitimate, unrelated file matching that glob in the temp dir would also
  be removed — considered acceptable since the daemon owns that naming
  convention exclusively.

## Migration Plan

No data migration. Existing `~/.config/whispy/config.json` files with a
persisted `language` key are unaffected by the default-language change.
Existing LaunchAgent-era guidance text is corrected in place (log
messages only, no state to migrate). No config schema changes.

## Open Questions

None outstanding — both commits are implemented, tested (568 passed), and
already on `feat/rebrand`. This document records the completed decisions
for future reference rather than proposing open work.

# Design — Refresh Audio Devices Before Capture

## Context

PortAudio enumerates audio devices exactly once, at `Pa_Initialize()` — which happens when `sounddevice` is imported, i.e. at daemon startup. The daemon then runs for days. When the system default input device changes afterwards (Bluetooth headset connects/disconnects, Mac sleeps/wakes), the cached default device reference goes stale and `sd.RawInputStream(...)` fails with `PaErrorCode -9986` (observed repeatedly in `~/.whispy.log`).

Today `AudioEngine.start()` (`src/whispy/core/audio.py`) catches the open failure, logs a warning, and returns `True` anyway: the state machine transitions to RECORDING, the UI animates, and nothing is captured. The user discovers the failure only when no text appears.

The engine already has an established pattern for surfacing async failures to the UI: `on_X(callback)` / `_notify_X(...)` pairs in `engine.py` (`on_model_load_failed`, `on_permission_missing`, `on_injection_permission_denied`), with the menu bar subscribing and posting a `rumps.notification`.

## Goals / Non-Goals

**Goals:**
- Capture always targets the *current* system default input device, across Bluetooth connect/disconnect and sleep/wake.
- A capture-stream open failure is visible to the user, not just in the log file.
- No behavior change on the happy path (same WAV format, same readiness wait, same state machine flow).

**Non-Goals:**
- Device picker / letting the user select a specific input device (follow-the-system-default stays the policy).
- Reacting to device changes *mid-recording* (a headset dying during an active recording keeps current behavior: the stream errors, the recording ends short).
- Linux-specific handling — the refresh is cross-platform PortAudio behavior, no per-OS branches.

## Decisions

### 1. Refresh PortAudio on every `start()`, not lazily on failure

Call `sd._terminate()` + `sd._initialize()` at the top of `AudioEngine.start()` (guarded for `sd is None` and wrapped in try/except so a refresh failure degrades to today's behavior).

- **Why not only-on-failure?** Refresh-on-failure still opens the first stream against a stale device: the -9986 costs one full failed recording attempt before recovery. Refresh-every-start makes the *first* press work. Re-init cost is tens of milliseconds — negligible next to the existing 2 s readiness timeout and model inference.
- **Why not `device=` with a fresh default query?** Querying the default through a stale PortAudio instance returns the stale answer; re-enumeration is required regardless. Once refreshed, the parameterless default is correct — no need to pass `device=` explicitly.
- **Private API caveat:** `sd._terminate()`/`sd._initialize()` are underscore-prefixed but are the documented community answer for device-list refresh (sounddevice exposes no public re-scan). Pin the usage with a unit-mocked test so a sounddevice upgrade that breaks it fails loudly.
- **Safety:** must never run while a stream is open. `start()` is guarded by the state machine (no re-entry while RECORDING), and the app opens no other PortAudio stream (the level meter reads from the same capture stream by design), so the refresh point is safe.

### 2. One retry after a second refresh on open failure

If `sd.RawInputStream(...)` still raises after the routine refresh, refresh once more and retry the open once. Covers the race where the device set changes between refresh and open (e.g. Bluetooth negotiation completing mid-start). Still-failing after retry → give up as today (empty recording path), but now notify (Decision 3).

### 3. Surface open failure via a new engine callback pair, mirror of `on_model_load_failed`

- `AudioEngine.start()` records the failure (e.g. `self._capture_failed: str | None`) instead of swallowing it; keep returning `True` so the state machine flow and UI animation stay untouched (the stop path already handles an empty recording).
- `engine.py` adds `on_capture_failed(callback)` / `_notify_capture_failed(message)` following the existing fan-out pattern, fired from the recording-start path when the audio layer reports the failure.
- The menu bar subscribes and posts the existing-style notification ("No microphone available — check your input device").

**Alternative considered:** make `start()` return `False` on stream failure and abort the recording. Rejected: changes state machine semantics and every caller's contract for a rare path; the notify-but-continue approach is a smaller diff and the empty-recording guard already exists downstream.

## Risks / Trade-offs

- [`sd._terminate()` mid-stream corruption if a stream is ever open elsewhere] → single-stream invariant is documented in `audio.py` (level meter piggybacks the capture stream); refresh only inside `start()` under the state-machine guard.
- [Private sounddevice API breaks on upgrade] → try/except around refresh degrades to current behavior; unit-mocked test pins the call so upgrades surface it.
- [Refresh latency on every press] → tens of ms, dwarfed by existing readiness wait; if it ever measurably matters, drop to refresh-on-failure-only (retry path already implements it).
- [Notification noise if device genuinely absent and user hammers hotkey] → acceptable for now; debounce like `_notify_injection_denied` (one per transition) if it annoys.

## Open Questions

- None blocking. Notification debounce left as a follow-up if needed.

## Context

`define-test-perimeter` tagged event-tap, restart, and visualization scenarios as `macos-real`/`manual-ui` because their logic is entangled with Quartz/rumps/sounddevice. But the *decisions* inside those call sites are pure: which keycode/flag combination means press vs release, which path the daemon script resolves to, what level an RMS sample maps to, which animation frame index to show. Extracting these makes them `unit-pure` without changing behavior. `pyproject.toml` currently omits all of `ui/*` and `hardware/event_tap.py` from coverage, so any pure helper left inside those is invisible to coverage even once tested.

## Goals / Non-Goals

**Goals:**
- Extract pure functions from OS call sites; cover them with `unit-pure` tests.
- Keep the OS shell (CGEventTap, rumps timer, sounddevice stream) calling the extracted functions, behavior-identical.
- Re-tier the now-backed scenarios and narrow the coverage omit so the new modules count.

**Non-Goals:**
- Changing any runtime behavior (pure refactor + tests only).
- Testing the irreducible OS calls themselves (that is step A).
- Writing semantic transcription tests (step B).

## Decisions

### Decision: Pure helpers live in non-omitted modules
Extracted logic goes into modules coverage does **not** omit; the OS shell imports them.

| Concern | Source shell (stays omitted) | New pure module (covered) | Extracted function |
|---------|------------------------------|---------------------------|--------------------|
| Fn decode + keycode name | `hardware/event_tap.py` | `hardware/event_decode.py` | `decode_trigger_event(event_type, keycode, flags, trigger_keycode) -> "press"\|"release"\|None`; `keycode_to_name(keycode) -> str` |
| Daemon path resolution | `ui/menu_bar.py` | `core/paths.py` | `resolve_daemon_script() -> Path`; `daemon_script_exists(path) -> bool` |
| Audio level math | `ui/audio_level.py` | `ui/level_math.py` | `rms_to_level(rms, prev_smoothed, smoothing) -> float` (normalize ×10 clamp 1.0, then EMA) |
| Animation frame | `ui/menu_bar.py` | `ui/unicode_anim.py` (already pure data) | `select_frame(frame_index, is_active) -> str` |

Rationale: `event_decode.py`/`core/paths.py`/`level_math.py` are import-only of stdlib, so they load and run on any platform — no Quartz/rumps/sounddevice import — and coverage sees them.

Alternative considered — keep functions in place and narrow omit to just the Cocoa classes: rejected for `event_tap.py` (the Quartz import guard makes the whole module awkward to import in CI) but **adopted** for `ui/` (see next decision).

### Decision: Narrow the coverage omit
Replace blanket `ui/*` omit with the specific Cocoa/rumps-bound files (`menu_bar.py`, `waveform_window.py`, `indicator_window.py`, `audio_level.py`). New pure modules (`ui/level_math.py`, and `ui/unicode_anim.py` which is already pure) become covered. `hardware/event_tap.py` stays omitted; `hardware/event_decode.py` is covered.

### Decision: Shells become thin delegators
`_event_callback` computes nothing itself — it reads event fields and calls `decode_trigger_event`, then dispatches. `_on_reload` calls `resolve_daemon_script`/`daemon_script_exists`. `_audio_callback` calls `rms_to_level`. `_tick_anim` calls `select_frame`. Each shell keeps only the I/O it cannot avoid (reading CGEvent fields, spawning the process, setting `self.title`, locking).

## Risks / Trade-offs

- **Behavior drift during extraction** → Mitigation: extract verbatim, assert via tests that the pure function reproduces the prior inline expression; run full suite (must stay 351+ green) before re-tiering.
- **`flags` tuple quirk** (pyobjc may return a tuple for `CGEventGetFlags`) → the tuple-unwrapping must move into `decode_trigger_event` so it is tested, not left in the shell.
- **Coverage omit narrowing surfaces low UI coverage** → expected and acceptable; the Cocoa files remain `manual-ui`. Do not chase coverage on them here.

## Open Questions

- Should `keycode_to_name`'s big mapping table move too, or stay in `event_tap.py` and be imported back? Default: move the table to `event_decode.py` (it is pure data) and re-export from `event_tap.py` for compatibility.

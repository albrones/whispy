## Why

On 2026-10-09, right after a `make reinstall`, four recordings in a row (72 s,
3 s, 1.7 s, then 2.4 s after a relaunch) captured only background noise: peak
level 0.03 to 0.055, against about 1.0 while talking. Whispy said nothing —
no text, and no end sound, since Pop only plays on success. The user took it
for a crash and relaunched. `~/.whispy.log` holds eight such recordings; the
existing hint (`at the noise floor`) used a 0.05 threshold and missed the 72 s
take at 0.055.

**Need, in one sentence:** when the microphone hears nothing, the user learns
it at the end of the recording, instead of guessing a crash.

## Framing (Régie Kanban card #145)

- When: at the end of the recording (not during it — thinking before speaking
  must not trigger an alert).
- How: a macOS notification naming the input device, plus a failure sound
  distinct from Pop (Basso).
- Threshold: peak level raised to 0.1; recordings under 0.5 s are ignored as
  accidental taps.
- The cause of the deaf microphone stays out of scope.

### Acceptance criteria

1. System Settings > Sound > Input: volume of « Micro MacBook Pro » at 0. Hold
   right ⌥ for 3 s saying « bonjour test »: on release, a notification
   (« Microphone heard nothing ») names « Micro MacBook Pro », a failure sound
   (not Pop) plays, no text is typed.
2. Input volume restored, dictate « bonjour test »: the text is typed, Pop
   plays, no alert.
3. A tap under 0.5 s on right ⌥ without speaking: no alert, no failure sound.
4. Tests: a take peaking at 0.055 (the 72 s take of Oct 9) triggers the
   warning, a take peaking at 0.2 does not; `make test` is green.
5. `~/.whispy.log` keeps the `capture closed … at the noise floor` line for
   each deaf take.
6. [in use] Next time the microphone goes deaf (after a `make reinstall` or a
   sleep), the alert arrives on the first take instead of blind relaunches.

## What Changes

- `AudioEngine.stop` flags a recording of at least 0.5 s whose peak stays under
  `NOISE_FLOOR_PEAK_LEVEL` (0.1) and exposes the input device name as
  `unheard_input`; the log hint uses the same threshold.
- `Engine.stop_recording` plays `Notifier.input_unheard()` and fans out
  `on_input_unheard` callbacks with a message naming the device.
- macOS menu bar posts « Microphone heard nothing »; the Linux notifier plays a
  freedesktop warning sound (the tray has no notification path yet).

## Raison d'être

- **Usage:** every dictation where the input is muted, turned down or stale —
  eight times in the log so far, several in a row each time.
- **Without it:** no text, no sound; the user relaunches Whispy, which does not
  fix a deaf input.

## Refusé

- **A live alert during the recording** — would fire while the user thinks
  before speaking.
- **Finding the cause of the deaf microphone** — unknown yet; a separate card
  if it repeats.
- **A Linux tray notification** — the tray has no notification path; the
  failure sound covers it.

## Coût

- No dependency, no network call, no served weight (desktop app). One system
  sound played through `afplay`/`paplay` on a deaf recording.

## Impact

- `src/whispy/core/audio.py`, `src/whispy/core/engine.py`,
  `src/whispy/platform/` (port + both notifiers), `src/whispy/ui/menu_bar.py`.
- Spec `audio-capture`: one requirement added.

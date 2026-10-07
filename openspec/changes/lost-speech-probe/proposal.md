## Why

`~/.whispy.log` holds 95 `Lost speech` warnings (and 52 older `Model returned no text` lines): clips that cleared every non-speech gate, reached the model, and came back empty even after the untrimmed retry. Over roughly 1,400 transcriptions that is about 7% of dictation lost without trace, and 34 of the 95 arrive in bursts — three consecutive 8 s chunks with 4.6–5.4 s of voice each, for instance — so this is not only short or quiet speech.

Two facts block any diagnosis today:

- **Successes are not logged** for whole recordings, so the loss rate cannot be read from the log.
- **Lost clips are deleted**, so every hypothesis (trim margin, gain, model state) is a guess that cannot be replayed.

Framing (Régie kanban card #100, answers chosen by the user):

- How the problem shows up: *I dictate and nothing gets typed, fairly often.*
- Expected outcome: *diagnose, then fix.*
- What to keep: *only lost clips, locally, capped at 20.*

## What Changes

This change is delivered in two PRs. The first (this one) adds the instruments; the second, once at least 10 real lost clips have been kept, writes the diagnosis and the fix.

- PR 1: log every successful transcription at INFO with the clip duration and the text length (never the text).
- PR 1: copy each lost clip into `~/.whispy/lost/` (owner-only directory), name it in the `Lost speech` warning, and keep only the newest 20.
- PR 1: `scripts/replay_lost.py` replays kept clips untouched, trimmed as Whispy trims, trimmed with a 1 s margin, and gain-normalized.
- PR 2: `research/lost-speech.md` names the measured cause, and the fix lands in the transcription path.

## Acceptance criteria

1. Dictate « bonjour, ceci est un test »: `~/.whispy.log` has an INFO success line with the clip duration, so successes and `Lost speech` lines can be counted in the same log.
2. A lost clip is written to `~/.whispy/lost/` and the `Lost speech` warning gives its file name; at the 21st, the oldest is deleted.
3. `python scripts/replay_lost.py ~/.whispy/lost/*.wav` prints, for each clip, the text returned (or empty) as is, then under each tested variant (gain normalized, untrimmed, wider margin).
4. `research/lost-speech.md` names the cause measured on at least 10 real lost clips, with the replay result table.
5. After the fix, replaying the kept clips returns text for at least 80% of them, and the existing tests (`make test`) stay green.
6. [à l'usage] Over a week of dictation, at most 1 `Lost speech` per 20 successes in the log.

## Rejected

- Keeping every clip behind a debug switch: it allows comparing successes with losses, but it keeps voice that was transcribed fine and needs manual cleanup.
- Only warning the user ("nothing understood, say it again"): it hides the loss instead of explaining it.
- Diagnosing from log metrics alone: without audio, every cause stays a hypothesis.

## Cost

No new dependency, no network call. At most 20 short WAV files (≈ 16 KB/s each, a few MB in total) in `~/.whispy/lost/`, readable only by the user.

## Capabilities

### Modified Capabilities

- `audio-capture`: a lost clip is kept for replay and named in its warning; a successful transcription is logged.

## Impact

- `src/whispy/core/audio.py` — `transcribe` logs successes and keeps lost clips.
- `scripts/replay_lost.py` — new diagnostic script.
- Tests: `tests/test_audio.py`, `tests/conftest.py`.

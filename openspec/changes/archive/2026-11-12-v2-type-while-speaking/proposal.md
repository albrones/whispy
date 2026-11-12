## Why

V1 has « Type while speaking »: in toggle mode, audio is cut at each pause and each piece is typed as soon as it is transcribed, so a long dictation shows up while the user is still talking. V2 transcribes nothing until the stopping press (`controller.rs`, `Action::StopCaptureAndTranscribe`), so the user waits for a long dictation and loses the habit V1 gave him. This is criterion 9 of the V2 card (Régie whispy #1), validated on 2026-11-12.

## What Changes

- In toggle mode with `type_while_speaking` on, V2 cuts the recording at pauses while it records, transcribes each piece with the default pipeline as soon as it is cut, and types it into the frontmost app in order. The stopping press transcribes and types the last piece.
- The menu gains V1's « Type while speaking » row under SETTINGS, with the trailing ✓, bound to V1's `type_while_speaking` key in `~/.config/whispy/config.json` (V1's default: on).
- Hold mode is unchanged: the whole dictation is transcribed and inserted on release.
- The bench gains a case: a French clip with a one-second pause between two sentences yields at least two pieces, in order, and the joined text has a word error rate no worse than one-block transcription.

## Acceptance criteria (validated 2026-11-12)

1. V2's menu has the « Type while speaking » row under SETTINGS, with ✓. It reads and writes `type_while_speaking` in ~/.config/whispy/config.json, the same setting as V1.
2. Toggle mode with the setting on: two sentences separated by a one-second pause, and the first is typed into TextEdit before the stopping press ([à l'usage], and proven on the bench: a French + silence + French clip gives at least 2 pieces, in order).
3. The final text is the pieces joined end to end, with no duplicate and no loss, and a word error rate on that clip no worse than one-block transcription.
4. Hold mode is unchanged: the text is inserted on release.
5. The v2/ gate is green, and a 180 s dictation stays under 1.5 GB of memory.

## Impact

- `v2/whispy-core` (segmentation at pauses, if not already there), `v2/whispy2` (controller, settings, menu model and menu bar), `v2/banc`.
- Specs: `v2-menu-bar-app`, `v2-settings`.
- No new dependency expected.

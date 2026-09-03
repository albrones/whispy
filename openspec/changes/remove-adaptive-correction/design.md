## Context

Adaptive correction shipped in `b18c8c6` and was gated off in the same release
cycle: its fixed-window alignment mislearned word→word shifts from ordinary
continued dictation and fed them back to Whisper as hotwords — a
self-reinforcing hallucination loop (see `FEATURE_MATRIX.md:75`). The kill
switch is `ADAPTIVE_LEARNING_ENABLED = False` in
`src/whispy/core/corrections.py:31`; every entry point early-returns behind it.
Meanwhile the website's "Learns your words" card and README's feature bullet
still advertise the behavior, and three OpenSpec capabilities spec it.

Current code surface:

- `src/whispy/core/corrections.py` — store, detection, hotwords, replacement
- `src/whispy/hardware/ax_reader.py` — AX snapshot used only by detection
- `src/whispy/core/engine.py` — import (`:34`), store init (`:261`),
  `hotwords=self._build_hotwords()` (`:540`), `_detect_corrections` (`:572+`),
  worker call order (detection runs first on press)
- `src/whispy/ui/menu_bar.py` — "Learned Words" submenu + `_rebuild_learned_menu`
- Tests: `tests/test_corrections.py`, `tests/test_engine.py`
  (`TestCorrectionDetection`, `TestAdaptiveLearningDisabledByDefault`),
  `tests/test_docs.py` references
- Docs: `README.md:13`, `FEATURE_MATRIX.md:75`, `website/index.html` card +
  absence of Trigger submenu in the demo

## Goals / Non-Goals

**Goals:**

- Site, README, and FEATURE_MATRIX only claim behavior that runs.
- Dead code deleted, not gated — the gate has already proven it won't be
  flipped back without a rewrite.
- The implementation knowledge is preserved in a GitHub issue (pointer to
  `b18c8c6`, failure mode, rewrite requirements) so deletion loses nothing.
- Menu-bar demo on the site reflects the real menu (Trigger submenu present,
  no Learned Words).
- `install.sh`'s Linux hint matches README/website (`xdotool xclip
  libportaudio2`).

**Non-Goals:**

- No reimplementation of correction learning (tracked in the issue).
- No change to manual vocabulary biasing via `initial_prompt`
  (`transcription-quality` keeps that channel).
- No migration/cleanup of existing `~/.config/whispy/corrections.json` files —
  orphaned config is harmless and deleting user files is riskier than leaving
  them.

## Decisions

1. **Delete, don't deepen the gate.** Alternative: keep the code behind the
   flag "for the rewrite". Rejected — the rewrite replaces the alignment core,
   so the preserved code has low salvage value, and dormant code keeps costing
   menu real estate, test time, and (as this change proves) doc drift. Git
   history + the issue preserve everything.
2. **GitHub issue before deletion, referencing the last-good commit.** The
   issue is the durable pointer (`git show b18c8c6`, files involved, the
   poisoning failure mode, "rewrite alignment first" as acceptance criterion).
   Created via `gh issue create` as an operational task — not spec-guarded.
3. **Remove the three capabilities via REMOVED delta specs** so archiving
   deletes `adaptive-vocabulary`, `correction-detection`, `correction-store`
   from `openspec/specs/`. Cross-referencing requirements in
   `transcription-quality`, `core-engine`, `text-cleaning`, `user-facing-docs`
   get MODIFIED deltas.
4. **`ax_reader.py` goes too.** Its module docstring says it exists for
   correction detection; verify no other importer at apply time (grep), delete
   with the feature.
5. **Website gains a negative guard, not just card removal.**
   `tests/test_website.py` asserts the page does not claim correction
   learning (e.g. no "learns your words" / "remembers it" copy), so the card
   can't quietly return while the feature is absent.
6. **install.sh hint gains `libportaudio2`.** sounddevice wheels do not bundle
   PortAudio on Linux; README (`:96`) and the website are correct,
   `install.sh:181` is the outlier. "Code wins" applies to behavior claims,
   not to a factually incomplete hint string.

## Risks / Trade-offs

- [Menu demo edit breaks the animated demo's JS/CSS timing] → the demo is
  hand-rolled HTML/CSS; change only the dropdown rows, run
  `tests/test_website.py`, and eyeball the animation locally.
- [`corrections.json` orphaned on user machines] → accepted; harmless 0600
  file, documented in the issue.
- [Some other code path imports `corrections.py` or `ax_reader.py`
  indirectly] → grep for importers before deleting; engine tests +
  full suite must stay green.
- [README/website disagree in wording after edits] → user-facing-docs delta
  requires docs to *not* advertise the feature; website guard test enforces
  the site side.

## Migration Plan

Single PR: issue first (operational), then code deletion + doc/site sync +
spec deltas, full test suite green. Rollback = revert the PR; the feature was
inert, so no runtime behavior changes for users either way.

## Open Questions

- None blocking. Issue wording finalized at apply time from `FEATURE_MATRIX.md:75`
  and `b18c8c6`'s commit message.
- Resolved: tracking issue created — https://github.com/albrones/whispy/issues/8

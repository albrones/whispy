## Why

The adaptive-correction ("Learns your words") feature is permanently gated off
(`ADAPTIVE_LEARNING_ENABLED = False` in `src/whispy/core/corrections.py`)
because its correction-detection heuristic poisoned the Whisper hotwords
channel with misaligned pairs. Yet the promotional website still advertises it
as a live feature, three OpenSpec capabilities spec dead behavior, and the
dormant code (store, detection, menu item) ships in every build. The site must
only claim what runs; the dead code must go, with its state preserved in a
GitHub issue for a future, properly-aligned reimplementation.

## What Changes

- **BREAKING (internal):** delete the adaptive-correction code paths — the
  `corrections.py` module (store, hotwords, apply, tracking), the
  `_detect_corrections` hook in `engine.py`, the accessibility snapshot used
  for detection, and the "Learned Words" menu in `menu_bar.py`. Their tests go
  with them.
- File a GitHub issue before deletion, capturing the implementation state as
  of commit `b18c8c6`, why it was gated off (correction-poisoning loop into
  Whisper hotwords), and what a safe reimplementation needs (rewritten
  alignment).
- Website: remove the "Learns your words" feature card; add the "Trigger"
  submenu to the animated menu-bar demo dropdown (it exists in the real menu);
  never depict a "Learned Words" menu item.
- Align the Linux dependency hint in `install.sh` with README and website:
  `sudo apt install xdotool xclip libportaudio2` (sounddevice needs the system
  PortAudio runtime on Linux — README and website are correct; install.sh's
  message is the outlier).
- Remove the correction-learning section requirement from user-facing docs
  (README) and drop the corresponding spec requirements.
- Keep `tests/test_website.py` green; add a cheap guard that the site does not
  claim correction learning.

## Capabilities

### New Capabilities

<!-- none -->

### Removed Capabilities

- `adaptive-vocabulary`: hotwords biasing from the correction store — feature
  deleted.
- `correction-detection`: post-injection accessibility snapshot + correction
  detection — feature deleted.
- `correction-store`: persistent `corrections.json` store — feature deleted.

### Modified Capabilities

- `transcription-quality`: drop the "vocabulary from the correction store via
  `hotwords`" biasing channel; `initial_prompt` biasing stays.
- `core-engine`: the key-pressed worker no longer performs correction
  detection; non-blocking requirement for the remaining work stays.
- `text-cleaning`: remove the "apply learned corrections after cleaning"
  requirement.
- `user-facing-docs`: remove the requirement that README documents the
  correction-learning feature; replace with a requirement that docs do not
  advertise it (pointer to the tracking issue is allowed).
- `promotional-website`: no "Learns your words" (or any adaptive-learning)
  claim; menu-bar demo shows the Trigger submenu and no Learned Words item;
  Linux install snippet on the site stays `xdotool xclip libportaudio2`.

## Impact

- Code: `src/whispy/core/corrections.py` (deleted), `src/whispy/core/engine.py`
  (detection hook removed), `src/whispy/ui/menu_bar.py` (Learned Words menu
  removed), platform accessibility-snapshot helpers if unused elsewhere.
- Tests: `tests/test_corrections.py` deleted; engine/menu/website tests
  updated; new website guard assertion.
- Docs/site: `website/index.html`, `README.md`, `install.sh` hint text,
  `CLAUDE.md` if it references the feature.
- Specs: three capability specs removed, five delta specs.
- Operational: one GitHub issue created via `gh` before code deletion.
- User data: existing `~/.config/whispy/corrections.json` files are orphaned
  (harmless); no migration.

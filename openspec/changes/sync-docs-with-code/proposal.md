## Why

An audit of the user-facing documentation against the current code found multiple
contradictions that mislead both users and contributors:

- **Wrong defaults.** README.md documents `language` default as `fr`; the code default
  (`src/whispy/core/config.py` `DEFAULT_CONFIG`) is `en`. The website already agrees with
  the code — only README is stale.
- **Unauthenticated API examples.** AGENTS.md's `curl http://localhost:9090/...` examples
  (and a matching one in `install.sh`) omit the `Authorization: Bearer` header the server
  actually requires (`src/whispy/api/server.py`); every example as written returns `401`.
  README already shows this correctly.
- **Wrong file attribution.** README says `PORT` is defined in `whispy_daemon.py`; it is
  defined in `src/whispy/api/server.py`.
- **Incomplete config reference.** README documents 4 of the 16 keys in `DEFAULT_CONFIG`
  (missing `beam_size`, `best_of`, `start_at_login`, `auto_detect_min_duration`,
  `min_recording_duration`, `custom_vocabulary`, `streaming_enabled`, `pause_ms`,
  `min_chunk_s`, `max_chunk_s`, `vad_aggressiveness`).
- **Platform description stuck on macOS-only.** AGENTS.md still frames the whole
  architecture, tech stack, and permissions model as macOS-only (`pyobjc`, `rumps`,
  `osascript`) even though the app also ships a Linux/X11 path (`pynput`, `pystray`,
  `Pillow`, `systemd --user`).
- **Undocumented shipped feature.** The adaptive-correction / "learns your words" feature
  (`src/whispy/core/corrections.py`, `custom_vocabulary`, `tests/test_corrections.py`) is
  promoted on `website/index.html` but has no row in `FEATURE_MATRIX.md` — which claims to
  be the project's single source of truth for what ships — and no mention in README.
- **Stale test inventory.** README lists `tests/test_stress.py`, which does not exist, and
  describes `tests/test_error_handling.py` as covering "sox, mic, model" when the sox
  backend was removed and the file only covers capture-backend and mic failures.
- **CHANGELOG language and structure violations.** CHANGELOG.md is written entirely in
  French, violating the repo's English-only policy (AGENTS.md), and has two competing open
  sections (`## [Non publié]` and `## [Unreleased]`) plus a stale top-level release-date
  header on a file whose newest section is unreleased.
- **Stale tooling comments.** `Makefile`'s `app` target help text says "ad-hoc-sign", but
  `packaging/macos/build_app.sh` prefers the stable self-signed "Whispy Local Signing"
  identity and only falls back to ad-hoc signing if that identity is absent. `install.sh`
  still has comments referring to a macOS LaunchAgent, though the design uses SMAppService
  and no LaunchAgent is ever created on macOS.

None of these are behavior bugs — the code is correct. The risk is entirely that
users and contributors trust the docs over the code and get burned (wrong default
language, `401`s copy-pasted from AGENTS.md, an undiscoverable feature, a changelog
half the team can't read).

## What Changes

- Fix README.md: `language` default (`fr` → `en`), `PORT` file attribution
  (`whispy_daemon.py` → `src/whispy/api/server.py`), expand the config table to all 16
  `DEFAULT_CONFIG` keys, remove the `tests/test_stress.py` row, correct the
  `test_error_handling.py` description, and add the adaptive-vocabulary / "learns your
  words" feature to the feature list.
- Fix AGENTS.md: reframe "Platform" as macOS + Linux/X11, add `pynput`/`pystray`/`Pillow`
  to the tech-stack list, add `Authorization: Bearer <token>` to every curl example, and
  reframe the Architecture section to describe both platforms instead of macOS-only.
- Fix `install.sh`: add the auth header to the smoke-test curl example; update the two
  comments (near the model-persistence note and the OS branch) that still describe a
  macOS LaunchAgent to match the SMAppService design already documented lower in the file.
- Fix `Makefile`: correct the `app` target's help text to describe the actual signing
  preference (self-signed cert first, ad-hoc fallback).
- Add a row for adaptive vocabulary / correction learning to `FEATURE_MATRIX.md`, matching
  the existing `adaptive-vocabulary`, `correction-detection`, and `correction-store`
  OpenSpec capabilities.
- Rewrite `CHANGELOG.md` in English, merge the two open sections into a single
  `## [Unreleased]`, and drop the stale top-level release-date header.
- Add `tests/test_docs.py`: guard tests that assert doc-code invariants (documented
  default matches `DEFAULT_CONFIG`, config table covers every key, no reference to
  nonexistent test files, CHANGELOG has no French section headers and only one open
  section).

## Capabilities

### New Capabilities
- `user-facing-docs`: user-facing documentation (README, AGENTS.md, FEATURE_MATRIX.md,
  CHANGELOG.md, and doc-adjacent tooling comments) SHALL accurately reflect the current
  code — defaults, authentication requirements, supported platforms, config surface,
  shipped features, and the existing test suite — and SHALL be written in English, with
  automated guards where a doc-code invariant can be checked mechanically.

### Modified Capabilities
- None. `promotional-website` was audited and found already accurate (correct default
  language, correct platform framing, adaptive-vocabulary feature already promoted) — no
  spec change needed there.

## Impact

- `README.md` — config defaults and table, PORT attribution, test inventory, feature list.
- `AGENTS.md` (symlinked from `CLAUDE.md`) — platform description, tech stack, curl
  examples, architecture framing.
- `FEATURE_MATRIX.md` — new row for adaptive vocabulary / correction learning.
- `CHANGELOG.md` — full English rewrite, single `[Unreleased]` section.
- `install.sh` — auth header on the smoke-test curl, LaunchAgent comment cleanup.
- `Makefile` — `app` target help text.
- `tests/test_docs.py` (new) — doc-code invariant guard tests.

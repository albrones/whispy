## 1. README.md

- [x] 1.1 Fix `language` default in the Configuration section: `fr` → `en` (matches
      `DEFAULT_CONFIG["language"]` in `src/whispy/core/config.py`).
- [x] 1.2 Fix the `PORT` attribution sentence: `whispy_daemon.py` → `src/whispy/api/server.py`.
- [x] 1.3 Expand the Configuration table to cover all 16 `DEFAULT_CONFIG` keys (add
      `beam_size`, `best_of`, `start_at_login`, `auto_detect_min_duration`,
      `min_recording_duration`, `custom_vocabulary`, `streaming_enabled`, `pause_ms`,
      `min_chunk_s`, `max_chunk_s`, `vad_aggressiveness`), one row each with a
      human-readable description and default value.
- [x] 1.4 Remove the `tests/test_stress.py` row from the test-file table (file does not
      exist).
- [x] 1.5 Fix the `tests/test_error_handling.py` description: drop "sox", describe actual
      coverage (capture-backend / microphone failures).
- [x] 1.6 Add a feature-list entry for adaptive vocabulary / "learns your words"
      (correction learning), consistent with `website/index.html`.

## 2. AGENTS.md (symlinked from CLAUDE.md)

- [x] 2.1 Rewrite the "Platform" line to state macOS + Linux/X11 instead of "macOS ...
      only".
- [x] 2.2 Add `pynput`, `pystray`, `Pillow` to the "Key Dependencies" list.
- [x] 2.3 Add `-H "Authorization: Bearer <token>"` (or equivalent placeholder) to each of
      the three curl examples (`/status`, `/start`, `/stop`).
- [x] 2.4 Rework the "Architecture & Workflow" section (daemon, Fn/trigger listener,
      text injection, permissions) to describe the Linux/X11 path (systemd --user,
      `pynput` listener, `pystray` UI) alongside the macOS path, instead of framing the
      whole section as macOS-only.

## 3. FEATURE_MATRIX.md

- [x] 3.1 Add a row for adaptive vocabulary / correction learning: feature name, tier,
      and "Verified by" pointing at `tests/test_corrections.py` (and any other existing
      coverage for `correction-detection`/`correction-store`), consistent with the
      `adaptive-vocabulary`, `correction-detection`, and `correction-store` OpenSpec
      capability specs.

## 4. CHANGELOG.md

- [x] 4.1 Translate every French entry (sections `## [Non publié]` through the rest of
      the file) into English, preserving meaning and chronology.
- [x] 4.2 Merge `## [Non publié]` and `## [Unreleased]` into a single `## [Unreleased]`
      section (de-duplicated, most-recent-first).
- [x] 4.3 Remove the stale top-level `**Date de release:** 2026-05-26` header (the newest
      section is unreleased, so a release date at the top is misleading).

## 5. install.sh / Makefile tooling comments

- [x] 5.1 In `install.sh`, add the bearer-token header (or a note on where to find the
      token) to the smoke-test `curl http://localhost:9090/status` example (~line 183).
- [x] 5.2 In `install.sh`, fix the comment near the model-persistence note (~line 111)
      that describes the daemon as running detached via "LaunchAgent/systemd" — macOS
      uses SMAppService, not a LaunchAgent.
- [x] 5.3 In `install.sh`, fix the OS-branch comment (~line 139, "macOS: a LaunchAgent
      below") to match the SMAppService design already documented later in the file
      (~line 190-194).
- [x] 5.4 In `Makefile`, fix the `app` target's help text (~line 55, "Build &
      ad-hoc-sign") to describe the actual preference: self-signed "Whispy Local
      Signing" identity first, ad-hoc fallback only if that identity is absent.

## 6. Guard tests

- [x] 6.1 Create `tests/test_docs.py` following the `tests/test_website.py` pattern
      (plain pytest functions reading doc files as text).
- [x] 6.2 Add a test asserting the README-documented `language` default equals
      `DEFAULT_CONFIG["language"]`.
- [x] 6.3 Add a test asserting every `DEFAULT_CONFIG` key has a corresponding row in the
      README Configuration table.
- [x] 6.4 Add a test asserting every test file path referenced in README.md's test table
      exists under `tests/`.
- [x] 6.5 Add a test asserting AGENTS.md's curl examples each include an
      `Authorization: Bearer` header (or the literal auth-header string).
- [x] 6.6 Add a test asserting CHANGELOG.md contains no French-language section markers
      and exactly one `## [Unreleased]` heading.
- [x] 6.7 Run `./.venv/bin/pytest tests/test_docs.py tests/test_website.py -v` and confirm
      all pass alongside the existing suite (`./.venv/bin/pytest`).

# Proposal

## Why

`README.md` is ~500 lines and speaks to three audiences at once (end users, contributors, agents). The one-line install, which is what turns a GitHub visitor into a user, is buried under signing-cert details, LaunchAgent cleanup and a test inventory. Meanwhile the user who is stuck — Fn does nothing, no text appears, a setting looks wrong — has to scan the whole file for the paragraph that matches their OS and symptom. Static Markdown cannot adapt to "I am on Linux" or "this check failed". An interactive, OS-aware documentation site aimed at users solves both: the README can shrink to a pitch and an install line, and the detail moves to pages that show only what applies to the reader.

The config reference has a second problem: defaults, accepted ranges and meanings live in three places (`DEFAULT_CONFIG`, inline `if` branches in `_validate_config`, Python comments). A generated config page — and any tool that offers values to a user — needs them in one machine-readable place, or it will drift from what the daemon actually accepts.

## What Changes

- **Config schema.** `src/whispy/core/config.py` gains a single `CONFIG_SCHEMA` declaring, per key: default, type, constraints (range, allowed values, cross-key rules) and a one-line user-facing description. `DEFAULT_CONFIG` is derived from it and `_validate_config` validates from it. Loading behavior is unchanged: the same inputs produce the same validated config and the same stderr warnings.
- **Docs generator.** A new stdlib-only script `scripts/build_docs.py` reads `CONFIG_SCHEMA`, the `doctor` check registry and hand-written page sources in `docs/src/`, and writes static pages to `website/docs/`. The generated HTML is committed; Vercel serves it without a build step.
- **Interactive user docs** at `/docs/`, user-focused:
  - a global macOS / Linux switcher, remembered across pages, that hides instructions for the other OS;
  - an install page with a copyable one-liner and a checkable step list (permissions on macOS, X11/xdotool on Linux);
  - a troubleshooting page: a symptom-driven decision tree whose leaves map one-to-one to `doctor` checks and end with "run `make doctor` to confirm";
  - a config page: a builder (toggles, sliders, selects bounded by `CONFIG_SCHEMA`) that produces a ready-to-paste `config.json`, plus a full reference table;
  - a streaming visualizer that shows, on an animated audio timeline, where `pause_ms`, `min_speech_s`, `soft_gap_ms`, `min_chunk_s` and `max_chunk_s` cut chunks;
  - a usage/FAQ page (trigger modes, logs, restart, uninstall).
- **Freshness guard.** A test fails when the committed `website/docs/` differs from the generator's output, or when a config key or `doctor` check has no documentation.
- **BREAKING (docs layout):** `README.md` is cut down to a short pitch, the one-line install, a link to the docs, platform support and licence. The Configuration table, detailed install, permissions walkthrough, troubleshooting and FAQ move to the docs site. The test-file inventory moves to `CONTRIBUTING.md`. Existing README guard tests are retargeted accordingly.
- **Site link.** `website/index.html` gets a "Docs" entry in the header nav.

Out of scope: contributor docs (architecture, HTTP API reference), an API playground calling `localhost:9090`, a docs search engine, translations, and any change to the Vercel build configuration.

## Capabilities

### New Capabilities
- `interactive-docs`: the generated, OS-aware user documentation site under `website/docs/` — its generator, its pages and widgets (OS switcher, install checklist, troubleshooting tree, config builder, streaming visualizer), and the guard that keeps the committed output in sync with its sources.

### Modified Capabilities
- `user-facing-docs`: the requirements that README.md carries the complete Configuration table and the test-file table are retargeted — the config reference moves to the generated docs (derived from `CONFIG_SCHEMA`), the test inventory moves to `CONTRIBUTING.md`, and README.md must stay short and link to the docs.
- `core-engine`: adds a requirement that one configuration schema is the single source of every key's default, accepted values and description, and that validation derives from it.
- `promotional-website`: the landing page header links to the documentation site.

## Impact

- **Code:** `src/whispy/core/config.py` (schema extraction; `DEFAULT_CONFIG` and `_validate_config` derive from it), `src/whispy/doctor.py` (each check gains a stable id and platform so docs can reference it; output unchanged).
- **New files:** `scripts/build_docs.py`, `docs/src/` (page sources and templates), `website/docs/` (generated HTML, `docs.js`, `docs.css`).
- **Docs:** `README.md` (shortened), `CONTRIBUTING.md` (gains the test inventory and the "regenerate docs" step), `website/index.html` (nav link), `CHANGELOG.md`.
- **Tests:** `tests/test_docs.py` (README guards retargeted to generated docs / CONTRIBUTING), new docs freshness and coverage tests, `tests/test_config_validation.py` (schema parity), `tests/test_website.py` (nav link).
- **Dependencies:** none added; the generator uses the Python standard library only.
- **Sequencing:** `fix-config-merge-on-save` touches the same part of `config.py` and should be archived first. `improve-discoverability` also edits `website/index.html` and may change the canonical domain; the docs use relative links so they are unaffected by the domain change.

# Tasks

## 1. Prerequisite

- [x] 1.1 Confirm `fix-config-merge-on-save` is archived (`openspec list --json` no longer lists it as in-progress) and branch from an up-to-date `origin/main`; if it is not archived, stop and report rather than building on top of it

## 2. Configuration schema

- [x] 2.1 Add the `ConfigKey` dataclass and `CONFIG_SCHEMA` to `src/whispy/core/config.py`, covering all 14 keys in the current `DEFAULT_CONFIG` order with default, kind, bounds (`ge`/`gt`/`le`/`gt_key`/`choices`), unit, group and a one-line user-facing description; keep the existing design comments beside each entry; verify `python -c "from whispy.core.config import CONFIG_SCHEMA; print(len(CONFIG_SCHEMA))"` prints 14
- [x] 2.2 Derive `DEFAULT_CONFIG` from `CONFIG_SCHEMA` (deep-copying mutable defaults) and verify a new test in `tests/test_config_validation.py` asserts the two have identical keys and values and every description is non-empty
- [x] 2.3 Rewrite `_validate_config` as a loop over `CONFIG_SCHEMA` in declaration order, keeping the per-kind normalisers and the exact stderr warning wording for `trigger` and `custom_vocabulary`; verify the existing `tests/test_config_validation.py` and `tests/test_engine.py` pass with no test edits
- [x] 2.4 Add tests for the schema-driven paths the old tests did not pin: `vad_aggressiveness` 4 falls back with a warning naming the key, and `min_chunk_s=2, max_chunk_s=1` makes `max_chunk_s` fall back; verify `./.venv/bin/pytest tests/test_config_validation.py` passes

## 3. Doctor check registry

- [x] 3.1 Add a `@check(id, name, platforms)` decorator in `src/whispy/doctor.py` that registers each check into `CHECKS` in definition order with static metadata, and apply it to all 9 checks; verify `make doctor` output is unchanged, by comparing it before and after on this machine
- [x] 3.2 Add a test in `tests/test_doctor.py` asserting every entry in `CHECKS` exposes a unique `id`, a `name` and a non-empty `platforms` tuple, without running the checks; verify `./.venv/bin/pytest tests/test_doctor.py` passes

## 4. Generator and page shell

- [x] 4.1 Create `scripts/build_docs.py` (stdlib only): load `docs/src/layout.html`, substitute each page fragment with `string.Template`, copy `docs.css`/`docs.js`, write to `website/docs/` with a generated-file header comment, sorted and deterministic; support `--check` (regenerate to a temp dir and diff); add a `make docs` target with `## ` help text; verify `make docs` twice produces no `git diff`
- [x] 4.2 Write `docs/src/layout.html` with the site header, docs nav (Install, Troubleshooting, Configuration, Usage), the macOS/Linux switcher and the inline `<head>` script setting `html[data-os]` from storage or the detected OS (all storage in try/catch); link `../styles.css` then `docs.css`; verify in a browser that switching OS persists to another page and that with JS disabled both OS blocks show with their badges
- [x] 4.3 Write `docs/src/docs.css`: sidebar layout, `[data-os]` hiding rules and no-JS badges, widget styles, reduced-motion rules, no horizontal scroll at 360px; verify at 360px and 1280px in a browser
- [x] 4.4 Add `tests/test_docs_site.py` with the freshness test (calls the generator's check function, failure message names `make docs`) and a determinism test; verify both pass after `make docs` and that editing a generated file by hand makes the freshness test fail

## 5. Pages and widgets

- [x] 5.1 Write `docs/src/install.html`: copyable one-liner, per-OS checklist (macOS: `make app` path, microphone, Accessibility, Input Monitoring, Start at login; Linux: X11 session, `xdotool`, clipboard tool, `systemd --user`), model download size, uninstall one-liner; checklist state in storage; content taken from the current README install and permissions sections; verify copy buttons place the exact command on the clipboard and ticked steps survive a reload
- [x] 5.2 Write `docs/src/troubleshooting.json` (symptom tree whose leaves reference doctor check ids, with per-OS fix text drawn from the current README Troubleshooting/FAQ) and render it as nested `<details>` with an "Run `make doctor` to confirm" line on every leaf; make generation fail on a missing or unknown check id; verify with a test that deletes one entry from a copy of the tree and expects generation to raise
- [x] 5.3 Write `docs/src/config.html` with the generated reference table (key, default, accepted values, description, grouped) and the embedded `config-schema` JSON; verify the table rows equal `CONFIG_SCHEMA` keys
- [x] 5.4 Implement the config builder in `docs.js`: one input per key bounded by the embedded schema (checkbox, select, number with min/max/step, text for `trigger`, tag list for `custom_vocabulary`), `gt_key` cross-check, output of only non-default keys with a copy button and a "merge into your existing file" note; verify a test in `tests/test_docs_site.py` feeds the builder's documented sample outputs (for example `{"trigger_mode": "toggle"}`) through `_validate_config` with no warning, and check by hand that 5 cannot be entered for `vad_aggressiveness`
- [x] 5.5 Implement the streaming visualizer in `docs.js`: a fixed sample timeline where each cut rule fires at the default values, the rule order of `Segmenter.feed`, `HARD_MAX_FACTOR` injected by the generator from `segmentation.py`, live update from the builder's `pause_ms`/`min_speech_s`/`soft_gap_ms`/`min_chunk_s`/`max_chunk_s`, an "illustration" label, static rendering under reduced motion; add a comment in `segmentation.py` pointing at the JS port; verify in a browser that raising `pause_ms` above a sample pause merges those chunks
- [x] 5.6 Write `docs/src/usage.html`: hold vs toggle trigger, logs location, restart, uninstall per OS, and the local API with bearer-token `curl` examples and the `PORT` attribution to `src/whispy/api/server.py`; verify the examples run against the local daemon after `make reinstall`
- [x] 5.7 Write `docs/src/index.html` (docs landing: what Whispy is in two lines, links to the four pages), run `make docs`, commit `website/docs/`; verify every docs page is keyboard-operable (switcher, tree, checklist, builder) and that `python -m http.server -d website` serves `/docs/` with all assets loading

## 6. README, CONTRIBUTING, guards and site link

- [x] 6.1 Move the test-file table from README.md into a "Test suite" section of CONTRIBUTING.md (keeping the `test_error_handling.py` scope wording) and add a "Regenerating the docs" note (`make docs`, never edit `website/docs/` by hand); verify every listed path exists
- [x] 6.2 Rewrite README.md to at most 120 lines: pitch, one-line installer right after the pitch, prominent links to the docs' install, troubleshooting and configuration pages, platform support (with the X11 note), model name, download size and languages, licence and model attribution; verify it renders on GitHub (`gh` preview or push to a branch)
- [x] 6.3 Retarget `tests/test_docs.py`: config completeness, removed keys and default values against `website/docs/config.html`; test table and `sox` checks against CONTRIBUTING.md; PORT attribution against `website/docs/usage.html`; add README length (≤120) and docs-link tests; keep the Parakeet and correction-learning tests on README; verify `./.venv/bin/pytest tests/test_docs.py` passes
- [x] 6.4 Add the "Docs" link (`docs/`) to the header nav of `website/index.html` and a link to `docs/install.html` in the install section; extend `tests/test_website.py` with a nav-link test and run the local-asset check over the docs pages too; verify `./.venv/bin/pytest tests/test_website.py` passes
- [x] 6.5 Add a CHANGELOG `[Unreleased]` entry (docs site, shorter README, config schema) and update the `AGENTS.md` website-sync rule to mention `make docs`; verify the CHANGELOG guard tests still pass

## 7. Integration

- [x] 7.1 Run the full suite and lint (`./.venv/bin/pytest`, `ruff check`, `ruff format --check`) and verify everything is green
- [x] 7.2 Run `make reinstall` and confirm the daemon still loads an existing `~/.config/whispy/config.json` with no new warnings in `~/.whispy-error.log`
- [ ] 7.3 After merge, verify the Vercel production deployment is READY (not CANCELED) and `curl -sI` on `/docs/`, `/docs/config.html` and `/docs/docs.js` returns 200

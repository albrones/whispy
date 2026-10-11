# Design

## Context

See proposal.md for motivation. Current state that shapes the approach:

- `website/` is a static site served by Vercel with `buildCommand: ""` and `outputDirectory: website`. Nothing runs at deploy time, so anything generated must be committed.
- `src/whispy/core/config.py` holds `DEFAULT_CONFIG` (14 keys) and `_validate_config`, a sequence of hand-written `if` blocks. Bounds live only in those branches: non-negative numbers, strictly positive numbers, `vad_aggressiveness` in 0..3, `trigger_mode` in {hold, toggle}, `trigger` as `None` / non-negative int / non-empty string (trimmed), `custom_vocabulary` as a filtered list of strings, and the cross-key rule `max_chunk_s > min_chunk_s`. Each rejection prints `[config] Invalid <key> '<value>', defaulting to <default>` to stderr; `trigger` and `custom_vocabulary` use slightly different wording.
- `src/whispy/doctor.py` has 9 check functions in a `CHECKS` list. Each returns `CheckResult(name, status, detail)`, so the check's display name and the fix text only exist inside the function body, and running a check probes the build machine. The generator cannot call checks to learn about them.
- `src/whispy/core/segmentation.py` implements the cut rules the visualizer illustrates: pause cut after `min_speech_s` of voiced audio and `pause_ms` of silence; soft cut once the chunk passes `max_chunk_s` and a `soft_gap_ms` gap appears; hard cut at `max_chunk_s * HARD_MAX_FACTOR` (1.5). `min_chunk_s` discards short chunks at transcription.
- The venv has no Markdown or templating library. `tests/test_docs.py` guards README sections by heading name (`Configuration`, `Testing`).
- `fix-config-merge-on-save` (15/16 tasks, manual check left) modifies the same `config.py` area.

## Goals / Non-Goals

**Goals:**
- One place declares each config key; validation, defaults, the reference table and the builder all read it.
- The generator is boring: stdlib only, deterministic, fast enough to run inside a test.
- Docs keep working with JavaScript off and opened from `file://`.

**Non-Goals:**
- A general static-site generator or Markdown pipeline.
- Running the real segmenter in the browser, or byte-exact parity between the visualizer and `segmentation.py`.
- Changing how `doctor` reports or exits.

## Decisions

### 1. Schema as a dict of small dataclasses in `config.py`

```
CONFIG_SCHEMA: dict[str, ConfigKey] = {
    "pause_ms": ConfigKey(default=600, kind="number", gt=0, unit="ms",
                          group="Streaming", description="Silence that closes a chunk."),
    "vad_aggressiveness": ConfigKey(default=2, kind="int", ge=0, le=3, ...),
    "trigger_mode": ConfigKey(default="hold", kind="choice", choices=("hold", "toggle"), ...),
    "max_chunk_s": ConfigKey(default=8.0, kind="number", gt_key="min_chunk_s", ...),
    "trigger": ConfigKey(default=None, kind="trigger", ...),
    "custom_vocabulary": ConfigKey(default=[], kind="str_list", ...),
    ...
}
DEFAULT_CONFIG = {k: copy(v.default) for k, v in CONFIG_SCHEMA.items()}
```

`kind` is one of `bool`, `number` (int or float, bool rejected), `int`, `choice`, `trigger`, `str_list`. Bounds are `ge` / `gt` / `le` plus `gt_key` for the one cross-key rule. `_validate_config` becomes a loop over the schema in declaration order, which keeps `min_chunk_s` validated before `max_chunk_s` as today. `trigger` and `str_list` keep their own normaliser and message, so warning text is unchanged. The long design comments currently above each default stay in the file, next to the schema entry; `description` is a separate user-facing sentence.

*Alternatives:* JSON Schema (more vocabulary than 14 keys need, and the validation library would be a new dependency); keeping `DEFAULT_CONFIG` and adding a parallel `CONFIG_DOCS` dict (that is the duplication this change removes); pydantic (new runtime dependency in the daemon).

### 2. Doctor checks register with static metadata

A `@check(id, name, platforms)` decorator appends to `CHECKS` in definition order and stores the metadata on the function. The generator reads `id`, `name` and `platforms` without running anything. The user-facing fix text for the docs lives in the troubleshooting source (decision 4), keyed by check `id`. Generation fails on an id with no entry or an entry with an unknown id. `doctor` output and exit codes do not change.

*Alternative:* parse check names out of the source with `ast` — fragile, and the fix text in `detail` is terse terminal text, not docs prose.

### 3. Stdlib generator, HTML fragments as sources

`scripts/build_docs.py` (run by `make docs`):

```
docs/src/
  layout.html            shared shell: head, header, OS switcher, nav, footer ($title, $body)
  index.html             landing for /docs/
  install.html           fragments with data-os sections
  troubleshooting.json   symptom tree; leaves reference doctor check ids
  usage.html
  config.html            prose around $config_table and $config_schema_json
  docs.css, docs.js      copied verbatim
        |
        v  string.Template substitution, sorted iteration, "\n" line endings
website/docs/{index,install,troubleshooting,config,usage}.html, docs.css, docs.js
```

Sources are HTML fragments, not Markdown: no parser dependency, and the widgets need custom markup anyway. `--check` regenerates into a temp dir and diffs against `website/docs/`; the freshness test calls the same function directly. The config schema is embedded in `config.html` as `<script type="application/json" id="config-schema">`, not fetched, because `fetch()` of a sibling file fails on `file://`. The troubleshooting tree is rendered as nested `<details>` elements, so it is usable without JS.

*Alternatives:* MkDocs (build step on Vercel, a Python docs toolchain to pin, and custom widgets would still be hand-written JS); generating at deploy time (would need a Vercel build command, which we are keeping empty).

### 4. OS-specific content via `data-os` attributes

Each OS-specific block carries `data-os="macos"` or `data-os="linux"`. A small inline script in `<head>` sets `<html data-os="...">` from `localStorage` or `navigator.userAgentData` / `navigator.platform`, before first paint, so there is no flash. CSS hides `[data-os]` blocks that do not match `html[data-os]`. With no JS, `html` has no `data-os`, nothing is hidden, and a CSS `::before` badge labels each block "macOS" or "Linux". All storage access is wrapped in `try/catch`.

### 5. Visualizer: a JS port of the cut rules on a fixed sample timeline

The page holds a fixed timeline of about 25 s of speech and silence segments at 30 ms resolution, chosen so each rule fires at the default values (a sentence pause, a short "oui" that `min_speech_s` defers, a run-on stretch that hits the soft cut, and one that hits the hard cap). `docs.js` applies the same rule order as `Segmenter.feed`. The generator injects `HARD_MAX_FACTOR` from `segmentation.py`, so constants cannot drift. The rules themselves can drift; the widget is labelled as an illustration (spec), and a comment in `segmentation.py` points at the JS port.

*Alternative:* precompute cut positions in Python for a grid of slider values — exact, but the output size grows with every parameter, and sliders would snap to grid points.

### 6. Styling reuses the site's tokens

Docs pages link `../styles.css` for the `:root` tokens (brand green, dark background, radius, font), and then `docs.css` for the sidebar layout and widgets. There is no copy of the palette.

### 7. Test retargeting

`tests/test_docs.py` keeps its helpers but points them at new sources:
- the config-table and defaults tests parse `website/docs/config.html`'s reference table;
- the test-table tests parse `CONTRIBUTING.md`;
- the PORT test reads `website/docs/usage.html`;
- new tests cover README length and links, freshness, check coverage, and schema/default parity.

`tests/test_website.py` gains the nav-link test and runs its local-asset check over the docs pages too.

## Risks / Trade-offs

- [Generated HTML is committed, so diffs are noisy and someone may edit `website/docs/` by hand] → a header comment in each generated file names the source and command; the freshness test fails on any hand edit.
- [The visualizer's JS rules drift from `segmentation.py`] → constants are injected, the widget is labelled "illustration", and a cross-reference comment sits in both files. Accepted, because it is teaching material, not a contract.
- [Schema refactor changes loading behavior subtly, e.g. a warning's wording or check order] → the existing `test_config_validation.py` must pass unmodified before any doc work. A new parity test asserts `DEFAULT_CONFIG` equals the schema defaults.
- [Merge conflict with `fix-config-merge-on-save`] → archive that change first. If it is not archived in time, rebase onto it, since it touches `save_config`/merge and not `_validate_config`.
- [The README's absolute docs link breaks when `improve-discoverability` moves the canonical domain] → the URL appears once in README, and the domain switch task already sweeps hard-coded URLs. Inside the site, links are relative.
- [Builder output pasted over an existing `config.json` drops keys the user had] → the builder emits only changed keys and the page says to merge them into the existing file. The daemon fills missing keys from defaults, so a partial file is still valid.

## Migration Plan

1. Archive `fix-config-merge-on-save`.
2. Schema extraction with tests green. This is a self-contained commit that can ship alone.
3. Doctor registration decorator. Self-contained too.
4. Generator, sources and generated `website/docs/`, with freshness and coverage tests.
5. Shrink the README, move the test table to CONTRIBUTING, retarget the guards, add the nav link, update the CHANGELOG.
6. After merge: check the Vercel production deployment is READY and `curl` `/docs/` and `/docs/config.html` for 200.

Rollback: revert step 5 to restore the long README. Steps 2–4 are additive or behavior-preserving.

## Open Questions

- The exact sample timeline for the visualizer (segment lengths). Tune while building, as long as each rule fires at default values.
- Whether `docs/src/` should also hold an "about the model" page. It can be added later without changing the generator.

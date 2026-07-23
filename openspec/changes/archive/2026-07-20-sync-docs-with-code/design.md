## Context

Whispy has an explicit "docs must track code" norm (AGENTS.md: "Keep the website in sync"
plus a repo-wide English-only policy) and a `FEATURE_MATRIX.md` that self-declares as the
"single source of truth for what works." An audit against the current codebase (commit
`f2b489a`, branch `feat/adaptive-transcription-memory`) found the norm isn't being
enforced: README, AGENTS.md, FEATURE_MATRIX.md, CHANGELOG.md, and a couple of tooling
comments have drifted from `src/whispy/core/config.py`, `src/whispy/api/server.py`, the
actual `tests/` directory, and the macOS signing/autostart implementation. There is
precedent for this exact failure mode — `openspec/changes/archive/2026-06-25-fix-user-facing-docs`
already fixed a different batch of doc/code mismatches (license text, sox references,
OG image, macOS-only framing on `CONTRIBUTING.md`) but only touched the
`promotional-website` spec; nothing in that change created a general "docs match code"
capability, which is why this class of regression recurred.

No existing spec covers README/AGENTS.md/FEATURE_MATRIX.md/CHANGELOG.md content. This
change introduces one (`user-facing-docs`) so future contributors have a spec to check
non-website doc claims against, and adds automated guards so the cheapest class of
drift (a default value, a missing config key, a deleted test file) fails CI instead of
waiting for the next manual audit.

## Goals / Non-Goals

**Goals:**
- Fix every concrete contradiction found in the audit (see proposal.md) in this same
  change, not as follow-up debt.
- Make the highest-value invariants mechanically checkable, so the fix doesn't silently
  regress next time `DEFAULT_CONFIG` gains a key or a test file is renamed.
- Bring CHANGELOG.md into compliance with the repo's English-only policy without losing
  the historical record of what shipped and when.
- Give FEATURE_MATRIX.md a row for the adaptive-vocabulary feature set, closing the gap
  between what the website promotes and what the "single source of truth" tracks.

**Non-Goals:**
- Rewriting or restructuring README/AGENTS.md/FEATURE_MATRIX.md beyond what's needed to
  fix the identified contradictions — this is a correctness pass, not a docs redesign.
- Building a general doc-generation pipeline (e.g., auto-generating the whole
  Configuration section from `DEFAULT_CONFIG` at build time). See Decision 2.
  Translating or otherwise touching `docs/SPECIFICATION.md`, `docs/ROADMAP.md`,
  `CONTRIBUTING.md` — those were already covered by `fix-user-facing-docs` and are
  out of scope unless the current audit flagged them (it didn't).
- Changing any runtime behavior. Every fix in this change is documentation, comments, or
  test additions; no `src/whispy/**` code changes.

## Decisions

### 1. CHANGELOG strategy: translate the whole file to English

**Choice:** Translate `CHANGELOG.md` in full to English, and merge `## [Non publié]` and
`## [Unreleased]` into a single `## [Unreleased]` section (union of both entry lists,
de-duplicated, most-recent-first), dropping the stale `**Date de release:** 2026-05-26`
header since the newest section is explicitly unreleased.

**Why over "translate only unreleased, freeze historical FR entries with a note":**
the repo's language policy ("all documentation... must be written in English") has no
carve-out for historical entries, and a changelog that's half French forever is a
permanent, visible policy violation rather than a one-time fix. The file is short (125
lines) — translating it once is cheaper than maintaining a "these old entries are
French, that's fine" exception indefinitely, and a mixed-language file is exactly the
kind of thing a future contributor copy-pastes from without noticing the language split.
The freeze-with-a-note approach was considered and rejected: it's less work now but it
leaves the violation on the books and requires every future reader to learn the
exception.

**Trade-off accepted:** this is a one-time translation task with no automated
verification of translation fidelity (a human/agent must read both versions and confirm
meaning is preserved) — mitigated by keeping it in the same PR as the rest of this
change so it gets reviewed alongside the other doc fixes.

### 2. Config docs: hand-written table, guarded by a parity test

**Choice:** Keep the README Configuration section as a hand-written Markdown table (one
row per `DEFAULT_CONFIG` key, in the same order as the dict), and add a guard test that
imports `DEFAULT_CONFIG` and asserts every key has a corresponding row in the table (by
parsing the table out of `README.md`) and that the documented `language` default string
matches `DEFAULT_CONFIG["language"]`.

**Why over generating the table from `DEFAULT_CONFIG` at build/doc time:** the config
keys need human-readable descriptions (what `vad_aggressiveness` does, why
`custom_vocabulary` exists) that don't exist in the code as docstrings suitable for
end-user consumption — generating from the dict alone would produce a table with no
useful prose, and adding structured per-key doc metadata into `config.py` is a bigger,
riskier change than this docs-sync pass warrants. A hand-written table with a mechanical
completeness/default-value check gets most of the safety (can't silently drop a key or
let a default drift) without a code-generation pipeline that would itself need
maintenance.

### 3. Guard tests: new `tests/test_docs.py`, following the `test_website.py` pattern

**Choice:** Add `tests/test_docs.py` as a new file, structured like the existing
`tests/test_website.py` (which already guards a handful of website/code invariants,
e.g. no `sox` references) — plain pytest functions that read the relevant doc file as
text (and import `DEFAULT_CONFIG` / walk `tests/` via `Path` where needed) and assert
specific strings/patterns are present or absent.

**Why a new file over extending `test_website.py`:** `test_website.py` is scoped to
`website/index.html`; these new checks span README.md, AGENTS.md, FEATURE_MATRIX.md,
CHANGELOG.md, and the `tests/` directory listing. Folding them into `test_website.py`
would make that file's name misleading and mix unrelated concerns. A dedicated
`test_docs.py` mirrors the project's existing per-concern test file convention
(`test_config_validation.py`, `test_auth.py`, etc.) and gives future doc-invariant checks
one obvious home.

**Why plain string/regex assertions over a Markdown parser:** the existing
`test_website.py` already uses simple substring/regex checks against file text
successfully; introducing a Markdown AST parser for this would be disproportionate to
the checks needed (presence/absence of strings, a key list diff against `DEFAULT_CONFIG`).

## Risks / Trade-offs

- **Translation risk:** translating 125 lines of French changelog by hand/agent risks
  subtle meaning drift. Mitigated by keeping the change reviewable in one PR and by the
  fact that changelog entries describe already-shipped, already-documented behavior
  elsewhere (commit messages, other specs) that can cross-check the translation.
- **Guard tests can only catch what they check.** `test_docs.py` guards the specific
  invariants enumerated in the spec (default value match, key-list completeness, no
  reference to nonexistent test files, CHANGELOG language/structure) — it is not a
  general anti-drift system. New doc claims introduced later still rely on the
  AGENTS.md "keep docs in sync" convention being followed; this change does not automate
  that away, only shrinks the blast radius of the highest-value, cheapest-to-check facts.
- **FEATURE_MATRIX row for adaptive vocabulary needs a "Verified by" target.** Per
  FEATURE_MATRIX.md's own maintenance rule, a new row must point at a real test. The
  feature already has `tests/test_corrections.py`; the task will point the row there
  rather than inventing new coverage, since the goal of this change is docs sync, not
  new test coverage for already-shipped behavior.
- **Scope creep risk:** the audit surfaced a few adjacent-but-out-of-scope issues (TODO.md
  recording French as a historical default, e.g.) that are explicitly left alone per the
  Non-Goals above; resisting the urge to "fix everything nearby" keeps this change
  reviewable.

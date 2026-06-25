---
name: validate
description: Run Whispy's release validation (preflight + live-drive + operator) and triage the result. Use when the user wants to verify the app actually works end-to-end on this machine, or asks "is the app broken / does everything still work".
license: MIT
compatibility: Requires the whispy repo, its .venv, and `make`.
metadata:
  author: whispy
  version: "1.0"
---

You are running and interpreting Whispy's release-validation system. The system
itself lives in `make validate` (source of truth); your job is to invoke it,
read the structured output, and triage — never to reimplement the checks.

## What the system does

Three honest layers for the host OS, with a three-state contract
(PASS / FAIL / UNVERIFIED — UNVERIFIED is never a silent pass):

1. **Preflight** — `doctor`: permissions, model cache, mic, xdotool, daemon.
2. **Live-drive** — boots the real daemon and drives a record→transcribe cycle
   over its HTTP API (no mocks).
3. **Operator** — guided human-in-the-loop checklist (the physical keypress +
   visual confirm). Skipped automatically when not attached to a TTY.

`FEATURE_MATRIX.md` is the single source of truth: every user-facing feature →
its coverage tier → how it is verified.

## Steps

1. **Pick the mode.** If the user can interact (and wants the full check), run
   the full system. If they want unattended/CI-style, skip the operator layer.
   - Full (interactive operator):
     ```bash
     make validate
     ```
     Note: the operator layer needs a real TTY. If you cannot provide
     interactive stdin, run unattended instead and tell the user the operator
     layer must be run by hand in their terminal.
   - Unattended (no human layer):
     ```bash
     make validate-unattended
     ```
   - Pass extra args via `ARGS`, e.g. `make validate-unattended ARGS="--no-live"`.

2. **Read the exit code — it is the verdict:**
   - `0` = PASS (everything exercised passed)
   - `1` = FAIL (a real defect — investigate)
   - `2` = UNVERIFIED (nothing failed, but seams could not be exercised — NOT a pass)

3. **Triage the summary.** For each non-PASS line, report: which layer, which
   feature, the tier, and the likely cause from the detail string. Distinguish
   clearly between FAIL (broken) and UNVERIFIED (untested-here). For UNVERIFIED,
   point at the preflight notes (e.g. "Microphone WARN → grant mic access").

4. **Surface matrix gaps.** The run prints a "Feature matrix lint" section. Any
   line there is a feature whose verification target is missing — name it.

5. **Remind the maintenance rule** when a fix or feature is in play: every change
   must update the `FEATURE_MATRIX.md` row AND add a regression case at the
   lowest tier that can catch the defect (pure-logic → unit-pure; seam →
   live-driven; human-only → manual-ui operator step).

## Guardrails

- Do not reimplement checks — `make validate` is the source of truth.
- Never report UNVERIFIED as success. A green-looking run with UNVERIFIED seams
  means those seams were not exercised here.
- If `make validate` itself errors (import/boot failure), report that as a tooling
  problem, not as a feature FAIL.

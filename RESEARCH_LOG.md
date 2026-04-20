---
name: research-log
description: >
  Automatic research session logger for agentic AI workflows. Retrospectively analyzes
  the full conversation history to detect blockers, retries, pivots, and results —
  then creates a structured markdown document in the /research/ directory.
  Use when the user says "log this session to research", "create a research note",
  "document what we did", or anything about capturing a research/development session.
---

# Research Log Skill — Automatic Session Analyzer for Local Documentation

You are an intelligent research session reconstructor. At the end of an agentic
development or research session, you analyze the entire conversation history to
automatically detect what happened — every approach tried, every tool call that
blocked, every correction made, every pivot, every result — and synthesize it into
a structured markdown file in the /research/ directory.

**The user should never need to manually annotate anything.** Your job is to be
smart enough to reconstruct the session narrative on your own, then present it to the
developer for review before writing the file.

---

## Step 1: Deep Conversation Analysis

**Read the entire conversation history from the beginning.** This is the most
important step — do not skip or skim it.

Your goal is to reconstruct the session narrative by detecting the following patterns:

---

### Pattern A — Agentic Blocker Chain

The most important pattern to detect. It looks like:

```
[User gives task/prompt]
  → [Agent executes tool calls]
    → [Tool call fails, hangs, returns unexpected output, or loops]
      → [User intervenes: "you got stuck", "fix this", "that didn't work",
         "you're blocked on X", "skip that", "try another way"]
        → [New approach begins]
```

For each Blocker Chain detected, capture:
- **The triggering prompt** (verbatim or near-verbatim)
- **The tool call(s) that failed** — what tool, what input, what error/output
- **The exact failure** — error message, unexpected output, infinite loop, wrong result
- **The user's correction signal** — what they said to unblock it
- **Why it blocked** — your interpretation (wrong parameters, API limitation, wrong approach, etc.)

---

### Pattern B — Approach Pivot

Signals: "let's try a different approach", "instead of X let's do Y", "forget that,
let's...", "actually let me rethink...", topic changes after failure, re-framing the goal.

For each Pivot detected, capture:
- **What was being attempted before** (the abandoned approach)
- **What triggered the pivot** (failure, new insight, user decision)
- **What the new direction is**

---

### Pattern C — Prompt Iteration / Refinement

Signals: Multiple prompts attempting the same goal with variations, user rephrasing
the same request, "make it more X", "that's not quite right, try...", adjusting
parameters or constraints across attempts.

For each iteration cluster, capture:
- **The goal** that was being iterated toward
- **The progression of prompts** (v1 → v2 → v3)
- **What changed** between versions and why
- **Which version worked** (if any)

---
### Pattern D — Successful Path

Signals: User says "great", "that works", "perfect", "ship it", "let's move on",
"yes that's what I wanted", or simply proceeds to the next task after a result.

For each Success, capture:
- **What approach/prompt led to it**
- **The concrete output** (file created, code written, result returned)
- **What made it work** compared to previous attempts

---

### Pattern E — Orphaned Explorations

Things that were tried but neither clearly succeeded nor clearly failed — abandoned
mid-way, inconclusive, or just not followed up on. These are easy to miss but
important for future researchers.

---

### Agentic Signal Vocabulary

These phrases in the conversation are strong signals — weight them heavily:

**Blocker signals:**
- "you got stuck on...", "you're blocked on...", "that didn't work"
- "fix this", "you seem to be looping", "that's wrong", "not what I wanted"
- "skip that for now", "let's work around this"
- Tool output contains: `Error`, `Exception`, `failed`, `timeout`, `undefined`, `null`
  when a value was expected, or an unexpectedly empty result

**Correction/retry signals:**
- "try again", "rephrase this", "try a different approach", "let me clarify"
- "actually...", "wait, no...", "I meant...", "instead of..."

**Success signals:**
- "perfect", "great", "exactly", "that works", "yes", "ship it", "nice"
- User immediately moves to the next task after a result

**Pivot signals:**
- "let's forget about X", "different approach", "start over on this part"
- "I'll do that manually", "we'll come back to this"

---

## Step 2: Git Context Enrichment

Run git commands to enrich what you found in the conversation:

```bash
git branch --show-current
git log --oneline --since="12 hours ago"
git diff --stat HEAD~10 HEAD 2>/dev/null | head -40
git stash list 2>/dev/null
```

Use this to:
- Confirm what files were actually changed (vs. what was attempted)
- Identify commits that correspond to "Result" moments in the conversation
- Detect stashed work that might represent abandoned approaches

---
## Step 3: Minimal Gap Interview

After your analysis, you should already have most of what you need. Only ask about
what's genuinely missing — keep it to 2–3 questions maximum.

Almost always missing (ask these):
1. **Participants** — "Who was working on this session?" (if not obvious from context)
2. **Duration** — "How long did this session run, roughly?"
3. **Next steps** — "What's the natural follow-up to this work?"

Sometimes missing (ask only if truly unclear):
- The high-level **objective** (if the session was exploratory without a clear goal)
- **External context** not in the conversation (things tried in other terminals, docs read, etc.)

Do NOT ask the user to describe what happened — you've already analyzed it. Your
questions should be the minimum needed to complete the picture.

---

## Step 4: Draft the Document & Determine Filename

Generate the complete document draft. Show it in full — the developer will review and
refine it before you save it. They know the context better than you; your job is to give them 90% of
the work so they just need to adjust.

### Filename convention and logic

You must determine the output filename based on context:
1. **Branch Context:** If a Git branch name is detected, slugify it (e.g., `feat/new-thing` -> `feat_new_thing`) and use: `SESSION_<branch-name_slug>.md`.
2. **Counter Context:** If the session is the Nth research log saved on this branch, use: `SESSION_X.md`. You must maintain an internal counter for the current topic/branch when creating this document.
3. **Default:** If no branch context is available, use: `SESSION_MAIN.md`.

The final file path must be in the `/research/` directory (e.g., `tools/research/SESSION_FEATURE_X.md`).

### Document body

```markdown
## 🔬 Research Session

| Field | Value |
|-------|-------|
| **Date** | {YYYY-MM-DD} |
| **Branch** | `{branch-name}` |
| **Duration** | {~X hours} |
| **Participants** | {names} |

---

## 🎯 Objective

{What this session was trying to achieve. 1–3 sentences.
If the goal evolved during the session, describe the evolution.}

---

## 🗺️ Session Narrative

{Chronological story organized by approach. This is the heart of the document.}

### Approach 1 — {Name}

**What was tried:**
{Description of the approach and why it seemed like the right path}

**Key prompt / instruction:**
> {Exact or near-verbatim prompt that launched this approach}

**Tool calls & what happened:**
- `{tool_name}({params})` → {what it returned or how it failed}

**Outcome:** {✅ Worked | ❌ Blocked | 🔄 Partial | ⏭️ Abandoned}

**What blocked it / why it was abandoned:**
{Exact error, unexpected behavior, or reason for abandonment}

**How it was unblocked:**
{User's correction signal, workaround, or decision to pivot}

---

### Approach 2 — {Name}

{Same structure — repeat for every approach}

---
## 🚧 Blockers Encountered

| Blocker | Triggered by | Root cause | Resolution |
|---------|-------------|------------|------------|
| {description} | `{tool or prompt}` | {why it happened} | {fix or workaround} |

_(Remove if no significant blockers)_

---

## ✅ Results

### Result A — {Title}
{Concrete output. Files, metrics, code, artifacts. Why it matters.}

### Result B — {Title}
{...}

_(Remove if session was purely exploratory)_

---

## 💡 Key Learnings

- ✅ **Do:** {What works and why}
- ❌ **Avoid:** {What doesn't work and why — the dead ends worth remembering}
- 💡 **Insight:** {Non-obvious discovery from the session}

---
## 🔜 Next Steps

- [ ] {Concrete next action}
- [ ] {Follow-up experiment with hypothesis}
- [ ] {Open question}

---

## 📎 References & Artifacts

- **Branch:** `{branch}`
- **Commits this session:** `{git log --oneline}`
- **Files touched:** {list}
- **External refs:** {docs, papers, links mentioned in conversation}
```

Then ask the user:

> "Does this capture what happened? Anything to add, remove, or correct before I save the document?"

## Step 5: Save the Document Locally

After confirmation, you must execute a file I/O command to persist the document in `/research/` using the determined filename. The agent should simulate this by using `edit_file`.

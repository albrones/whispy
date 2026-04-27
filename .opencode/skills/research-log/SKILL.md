---
name: research-log
description: >
  Auto-trigger on: create, ticket, linear, crée, envoi, wrap, finish, termine, log, research, session, pitch, agenda, audit, document, track, investigate, explore, analyze, implement, build, install, configure, fix, debug, migrate, refactor, test, optimize, architecture, design.
  Live session journal updated after every response turn that involved tool use or file changes.
  Follows the "AI Research Pitch" template, compatible with Linear ticket creation via MCP.
  Appends a new entry to section 3 each time the agent completes an action — not just at session end.
  Creates the log on first action, then appends incrementally. Never rewrites from scratch mid-session.
---

# AI Research Pitch — Per-Turn Live Logger

You are a live notepad. Your job is to **record what just happened** after every response where you used a tool, edited a file, ran a command, or produced an artifact.

The output format follows the **AI Research Pitch** template so it can be sent directly to Linear (via MCP) at session end.

**Core rule:** After every response turn that involved any action → update the log. Silently. No announcement, no permission needed.

---

## When to Update (Per-Turn Trigger)

**ALWAYS update after a response turn that included ANY of:**
- `edit_file`, `create_directory`, `copy_path`, `move_path`, `delete_path`
- `terminal` (any shell command)
- `read_file` when used to take action (not just orientation)
- Any Linear / MCP tool call
- `open`, `fetch`, `spawn_agent`
- A file was created, modified, or deleted as a side effect

**NEVER update after a response turn that was ONLY:**
- A pure text answer with zero tool calls
- A clarifying question to the user
- A permission request ("Can I do X?", "Should I proceed?")
- A summary or status report with no actions taken

---

## Log File Location and Naming

- Path: `research/SESSION_<topic-slug>_<YYYY-MM-DD>.md`
- **Topic slug**: 3–5 word kebab-case summary of the session's objective, inferred from the **first user instruction** of the session
- **Date**: today's date in ISO format (`YYYY-MM-DD`), captured at session start via the system clock or `date +%F`
- Example: working on "tester Claude Code pour génération de slides" on 2025-07-10 → `SESSION_test-claude-code-slides_2025-07-10.md`
- If the topic is truly ambiguous on the first turn: use `SESSION_misc_<YYYY-MM-DD>.md`
- If multiple distinct sessions happen on the same day with the same topic: append `-2`, `-3`, etc.

---

## Create vs Append Logic

```
First turn of the session:
  1. Infer topic from the user's first instruction → build <topic-slug>
  2. Capture today's date → <YYYY-MM-DD>
  3. Target file: research/SESSION_<topic-slug>_<YYYY-MM-DD>.md
     - Does it exist?
         NO  → Create it with the full skeleton (see Structure below) + first Turn entry under section 3
         YES → Append a new Turn entry under section 3 (continuing a same-day session on the same topic)

Subsequent turns in the same session:
  → Append only a new Turn entry under section 3 "Ce qu'on a fait"
  → Also update section 5 "Démo" if the turn produced a key artifact
  → Also update section 7 "Next Steps" if the turn revealed a clear follow-up action
  → Ensure the `model` list in the frontmatter includes your current model name
  → Ensure the H1 title does not contain the "AI Research Pitch — " prefix (remove it if present)
```

**Never rewrite the whole file mid-session.** Only append to section 3, and update sections 5 and 7 as needed.  
**Never rename the file mid-session** — the name is fixed at turn 1.

---

## Turn Entry Format

Each turn gets one entry appended under `## 3. Ce qu'on a fait` :

```markdown
### Turn N — <short topic label> · <tool(s) used>

**Instruction :** <one sentence: what the user asked or what triggered this turn>

**Actions :**
- `<tool>(<key param>)` → <outcome in one line: OK / FAIL / partial result>
- `<tool>(<key param>)` → <outcome>

**Output :**
- <file created or modified, or artifact produced — "aucun" if nothing>

**Blockers :** <"aucun" or brief description of what failed and how it was resolved>
```

Keep each entry **compact** — 5 to 15 lines max. Do not narrate, just list facts.

---

## Full Log Skeleton (used only when creating a new file)

```markdown
---
date: [date]
branch: [branch_name]
topic: [topic]
model: [liste model llm utilisée]
---

# <Sujet inféré depuis la première instruction>

## 1. Hook

> _Insight fort ou contre-intuitif — à compléter en cours de session ou au wrap-up_

---

## 2. Pourquoi on a exploré

> _Contexte + enjeu — inféré depuis la première instruction de l'utilisateur_

<objectif inféré en une phrase>

---

## 3. Ce qu'on a fait (et avec quels outils)

<!-- Les turns sont ajoutés ici automatiquement après chaque action -->

---

## 4. Ce qu'on a appris

✅ **Ce qui marche :** _À compléter au wrap-up_

❌ **Ce qui ne marche pas :** _À compléter au wrap-up_

🔥 **Ce qui change la donne :** _À compléter au wrap-up_

---

## 5. Démo

> _1 use case simple — mis à jour dès qu'un artefact clé est produit_

_À compléter_

---

## 6. Opportunités Zenika

**Mission 1 :** _À compléter_

**Mission 2 :** _À compléter_

**Offre potentielle :** _À compléter_

---

## 7. Next Steps

> _Call to action — mis à jour à chaque turn qui révèle une action claire_

- [ ] _À compléter_

---

## Références & Artefacts

<!-- Fichiers touchés, URLs, tickets Linear référencés -->
```

---

## Sections 5 & 7 — When to Update Mid-Session

Update **section 5 "Démo"** in the same append pass whenever the turn produced:
- A new file saved to disk that could serve as a demo
- A passing test or validation result
- A shipped artifact (slide deck, PR, document, generated code, etc.)

Update **section 7 "Next Steps"** whenever the turn revealed a clear follow-up action not yet in the list.

---

## Session Wrap-Up (explicit only)

When the user says "wrap up", "we're done", "c'est bon", "ship it", or explicitly asks for a full session summary:

1. Do a **consolidation pass** on the existing log:
   - Fill in **section 1 "Hook"** — synthesize the most surprising or counter-intuitive finding from the turns
   - Fill in **section 4 "Ce qu'on a appris"** — ✅ what worked, ❌ what didn't, 🔥 what's a game-changer
   - Fill in **section 6 "Opportunités Zenika"** — infer mission types and potential offers from the session context
   - Clean up **section 7 "Next Steps"** — remove done items, add final call to action
   - Update **"Références & Artefacts"** with all files touched
2. Run `git diff --stat HEAD 2>/dev/null | head -30` to cross-check changed files
3. Save the consolidated file
4. Inform the user: `📝 Session wrapped → research/SESSION_<slug>.md` + 3-bullet summary

Do **not** do the consolidation pass automatically mid-session — only on explicit wrap-up signal.

---

## Linear MCP Integration (creation & per-turn sync)

> ✅ **Validé en conditions réelles** — la connexion MCP via `save_issue` et `update_issue` est opérationnelle. Le ticket ZEN-19 a été créé directement depuis un fichier de session, sections 1–7 mappées en description Linear, sans aucune étape manuelle.

### 1. Automatic Sync (Per-Turn)
If the session log has an associated Linear ticket (e.g. a Linear ticket URL or ID is present in the `Références & Artefacts` section or frontmatter), **you must automatically update the ticket** after every action turn:
1. Use the `update_issue` MCP tool (or equivalent issue update tool).
2. Update the issue's description to match the latest contents (sections 1-7) of the session log.
3. Use the `save_comment` MCP tool (or equivalent) to add a comment to the issue containing the newly added Turn entry (the modifications just added to the log).
4. Do this silently, in the same pass as appending the log to `section 3`. No permission needed. Keep the ticket perfectly in sync with the file.

### 2. Issue Creation (at wrap-up or on request)
When the user says "crée le ticket", "envoie sur Linear", or "créer le ticket Linear", immediately:

1. **Read the current session file** — use the in-memory content if already loaded
2. **Discover the workspace** (in parallel):
   - `list_teams()` → identify the right team (infer from context or ask if ambiguous)
   - `list_issue_labels(team: <team>)` → pick the most relevant label(s)
3. **Consolidate missing sections** before sending:
   - If section 1 "Hook" is still a placeholder → fill it from the session turns
   - If section 4 "Ce qu'on a appris" is still a placeholder → fill it
   - If section 6 "Opportunités" is still a placeholder → fill it
   - Update the session file with the consolidated content
4. **Create the issue** via `save_issue`:
   - **title**: `<Sujet>`
   - **description**: full content of the session file (sections 1–7), in Markdown
   - **labels**: pick from available labels (prefer `Feature` or `Improvement` for research pitches)
   - **team**: as identified in step 2
5. **Confirm** to the user with the ticket identifier and URL
6. **Update the session file** — add the ticket URL to "Références & Artefacts", mark the Next Steps item as done

This bridges the session log directly to the Linear backlog without copy-paste.

---

## Git Context

At log creation time (first turn), capture:
- `date +%F` (today's date — used in filename and frontmatter)
- `git branch --show-current` (recorded in frontmatter for reference, not used in filename)

At wrap-up time, also capture:
- `git diff --stat HEAD~5 HEAD 2>/dev/null | head -30`

---

## Edge Cases

| Situation | Behaviour |
|-----------|-----------|
| Multiple tool-using turns in quick succession | One entry per turn under section 3 — do not merge |
| Turn failed entirely (all tools errored) | Still append the entry — blockers under section 3 are valuable |
| User asks "did you log that?" | Check the file and report what's there; update if missing |
| Session log exists from a previous session on same topic+day | Append with a `---` separator and a `## Session reprise — <heure>` heading before the new turn |
| No git repo / detached HEAD | Topic slug still applies; branch = "N/A" in frontmatter |
| Purely exploratory reads (no action taken) | Skip — do not log orientation-only turns |
| User asks to send to Linear | Use `save_issue` MCP tool (if creating) or `update_issue` (if already linked) with the full pitch content as description |

## Context

The `research-log` skill lives at `.agents/skills/research-log/SKILL.md`. It is loaded via the auto-discovery mechanism in AGENTS.md, which scans `.agents/skills/` at session start. Currently, the skill's `description` field contains keyword triggers that act as a filter — the skill only activates if the user's first prompt matches one of those keywords.

## Goals / Non-Goals

**Goals:**
- Make `research-log` trigger on every session, regardless of user prompt content
- Keep the mechanism simple — no new dependencies or infrastructure

**Non-Goals:**
- Generalizing the trigger system for all skills (this is scoped to `research-log`)
- Adding user configuration or opt-in/opt-out per session

## Decisions

### Decision: Add `trigger: always` to frontmatter, update AGENTS.md loader
- **Why:** Minimal change. The `trigger` field in YAML frontmatter is a natural extension of the existing `description` field. AGENTS.md already parses the skill directory — we just add one more condition.
- **Alternatives considered:**
  - Remove the keyword filter entirely from research-log → too fragile, no way to make some skills conditional
  - Create a separate "permanent skills" list in AGENTS.md → adds maintenance burden, duplicates info

### Decision: Keep keyword triggers on research-log for backward compatibility
- **Why:** The keyword triggers still work as a fallback. `trigger: always` means "load regardless", keywords mean "also load on match". No behavior is lost.

## Risks / Trade-offs

[Risk] Research-log fires on every session, even trivial ones (e.g., "what's in this folder?")
→ Mitigation The log entries are compact (5-15 lines) and only written when tools are used. Pure text responses don't trigger logging per the skill rules.

[Risk] User might not want logging for a specific session
→ Mitigation User can say "disable research-log" or remove the skill file. No opt-out mechanism needed for v1.

## Why

The `research-log` skill currently only triggers when the user's prompt contains specific keywords (e.g., "fix", "log", "investigate"). This means sessions involving tool use and file edits go unlogged simply because the user didn't use a matching keyword. The skill should be active for every session to ensure consistent research logging.

## What Changes

- Add a `trigger: always` field to the `research-log` skill's YAML frontmatter
- Update the AGENTS.md skill loading logic to recognize `trigger: always` and load the skill unconditionally at session start
- Document the new trigger behavior in the skill loading section of AGENTS.md

## Capabilities

### New Capabilities
- `skill-triggers`: Define the skill trigger mechanism, including the `always` trigger type and AGENTS.md loading logic

### Modified Capabilities
- None

## Impact

- `.agents/skills/research-log/SKILL.md` — add `trigger: always` to frontmatter
- `AGENTS.md` — update skill loading instructions to handle `trigger: always`

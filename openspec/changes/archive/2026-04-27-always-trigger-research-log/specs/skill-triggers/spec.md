## ADDED Requirements

### Requirement: Skill trigger mechanism supports `always` trigger

The skill loading system SHALL recognize a `trigger: always` field in a skill's YAML frontmatter. When present, the skill SHALL be loaded unconditionally at session start, regardless of the user's prompt content.

#### Scenario: Skill with `trigger: always` is loaded every session
- **WHEN** a skill's frontmatter contains `trigger: always`
- **THEN** the skill is loaded at the start of every session, even if the user's prompt contains no matching keywords

#### Scenario: Keyword triggers still work alongside `always`
- **WHEN** a skill has both `trigger: always` and keyword-based triggers in its `description`
- **THEN** the skill is loaded unconditionally, and keywords are treated as additional (non-blocking) metadata

### Requirement: AGENTS.md skill loader handles `always` trigger

The skill loading logic described in AGENTS.md SHALL check for `trigger: always` in each skill's frontmatter before applying keyword-based filtering. Skills with this trigger shall bypass the keyword filter.

#### Scenario: Loader loads `always` skill without keyword match
- **WHEN** the AGENTS.md auto-discovery scans a skill directory with `trigger: always`
- **THEN** the skill is applied to the session without requiring any keyword match in the user's prompt

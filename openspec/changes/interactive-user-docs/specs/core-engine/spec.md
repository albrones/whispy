## ADDED Requirements

### Requirement: One configuration schema is the single source of truth
Every configuration key's default value, accepted values and user-facing description SHALL be declared once, in a single machine-readable configuration schema. The default configuration and configuration validation SHALL both derive from that schema, so that a key cannot be added, removed or re-bounded in one without the other.

#### Scenario: Defaults derive from the schema
- **WHEN** the default configuration is compared with the schema
- **THEN** it has exactly the schema's keys, each with the schema's default value

#### Scenario: Validation follows the schema bounds
- **WHEN** a configuration file sets `vad_aggressiveness` to 4, outside the schema's range of 0 to 3
- **THEN** loading replaces it with the schema default and prints a warning naming the key, as before

#### Scenario: Every key is described
- **WHEN** the schema is inspected
- **THEN** every key has a non-empty description written for users

### Requirement: Schema extraction preserves loading behavior
Moving validation onto the schema SHALL NOT change which values are accepted, how accepted values are normalised (trimmed trigger strings, filtered vocabulary), the default a rejected value falls back to, or the cross-key rule that `max_chunk_s` must exceed `min_chunk_s`.

#### Scenario: Existing validation cases still hold
- **WHEN** the existing configuration validation tests run against the schema-driven loader
- **THEN** they pass unchanged

#### Scenario: Cross-key rule survives
- **WHEN** a configuration sets `min_chunk_s` to 2 and `max_chunk_s` to 1
- **THEN** `max_chunk_s` falls back to its default, exactly as before the change

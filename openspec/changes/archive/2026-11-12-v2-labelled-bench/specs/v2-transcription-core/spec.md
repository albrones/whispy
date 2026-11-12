## ADDED Requirements

### Requirement: The bench scores V2 on the user's labelled clips

`banc --labelled [dir]` SHALL replay every reviewed clip of the directory
(`<id>.wav` with `<id>.json` holding `ref`, `kind` of chunk, noise or
dictation) through the default pipeline and report, next to V1's
`baseline.json`: the lost chunk clips that came back with text, the noise clips
that got text, and the word error rate over chunk and dictation clips. The word
error rate SHALL use V1's text normalization so both sides compare. It SHALL
read the clips and write nothing, and exit non-zero when any part fails.

#### Scenario: Lost speech is counted against the 70 % target

- **WHEN** at least 70 % of the lost chunk clips come back non-empty
- **THEN** part (a) reports "holds", otherwise "NOT MET" with the counts

#### Scenario: Invented text on noise is reported

- **WHEN** a noise clip comes back with text
- **THEN** part (b) reports it as NOT MET, with V1's count beside it

#### Scenario: Words are compared the way V1 compares them

- **WHEN** a reference holds an apostrophe, a hyphen or an accent
- **THEN** it is split into words by V1's rule (`a-z`, digits and `à-ÿ` kept, the rest a space)

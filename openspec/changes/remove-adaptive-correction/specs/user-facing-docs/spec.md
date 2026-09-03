## MODIFIED Requirements

### Requirement: Feature documentation parity
FEATURE_MATRIX.md and README.md SHALL each have an entry for every capability that is
promoted on `website/index.html` and has a corresponding OpenSpec capability spec.
Neither document SHALL advertise adaptive correction learning ("learns your words")
while that feature is absent from the codebase; a pointer to the tracking issue is
permitted.

#### Scenario: Promoted feature has a FEATURE_MATRIX row
- **WHEN** a reader consults `FEATURE_MATRIX.md` for a feature promoted on the website
  (e.g. the configurable trigger key, specced by `trigger-selection-ui`)
- **THEN** a row exists naming the feature, its tier, and a "Verified by" target that
  points at existing coverage

#### Scenario: Docs do not advertise correction learning
- **WHEN** a reader consults README.md's feature list and FEATURE_MATRIX.md
- **THEN** no entry claims that Whispy learns from user corrections; at most a
  reference to the reimplementation tracking issue appears

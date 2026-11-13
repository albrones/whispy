## MODIFIED Requirements

### Requirement: The bench compares V2 with V1 and picks the default

`cargo run --release --bin banc` SHALL replay the lost clips of `~/.whispy/lost/`, the reference clips with a known text, their quiet copies and non-speech clips through every engine and strategy, alone and with the other engine as fallback, and through V1's own engine; it SHALL report per configuration the share of clips with text, the word error rate, latency p50 and p95 and the ~5 s sentence p95, write `v2/bench/REPORT.md` naming the pick, and exit non-zero when the pick differs from the core's default. When the user's labelled clips are on the machine (`~/.whispy/bench`), the bench SHALL also replay them through every configuration, each as a whole pipeline (split and joined as the app does), and rank the pick on them before any unlabelled clip: a configuration that returns text on a clip labelled noise SHALL be out; then one that holds criterion 3 on those clips, the most lost speech clips with text and the fewest word errors SHALL come first. The unlabelled lost clips SHALL rank only when there are no labelled clips. Only counts from the labelled clips SHALL reach the report.

#### Scenario: Text on unlabelled lost clips does not move the pick

- **WHEN** one configuration returns text on more unlabelled lost clips and another recovers more of the lost speech the user labelled, with fewer word errors
- **THEN** the pick SHALL be the second

#### Scenario: Text on a clip labelled noise rules a configuration out

- **WHEN** a configuration returns text on a clip the user labelled noise
- **THEN** it SHALL NOT be the pick while another configuration returns none

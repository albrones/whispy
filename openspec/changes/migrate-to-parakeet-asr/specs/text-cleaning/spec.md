## ADDED Requirements

### Requirement: Near-miss custom vocabulary correction
The system SHALL correct transcription output toward the user's configured `custom_vocabulary` after transcription and before injection. A token SHALL be replaced by a configured term when **either** its spelling is close to that term **or** it sounds like it. Both signals SHALL be computed with the standard library (`difflib`, `unicodedata`) — no new dependency. When `custom_vocabulary` is empty or absent, cleaning SHALL apply whitespace normalization only. Tokens shorter than **4 characters** SHALL be skipped entirely, which removes coincidental matches such as "on"~"onnx" (0.667) structurally.

Two signals are required because neither separates the classes alone. Spelling cannot: against a vocabulary of {Whispy, Parakeet, OpenSpec, onnx, Zenika} the false match "pense"~"OpenSpec" (0.769) outscores the true matches "parakite"~"Parakeet" and "paraquet"~"Parakeet" (both 0.750). Sound can: reduced to a consonant skeleton, "parakite" and "parakeet" are identical (1.000) while "pense" and "openspec" fall to 0.667.

The character cutoff SHALL be **0.80** and the phonetic cutoff SHALL be **0.90**. The phonetic bar SHALL be the stricter of the two because sound is the looser signal — measured over `/usr/share/dict/words` (234 335 entries of 4+ letters) against an eight-term vocabulary:

| rule | false positives |
|---|---|
| char ≥0.80 alone | 31 (0.013%) |
| phon ≥0.80 alone | 1763 (0.752%) |
| phon ≥0.90 alone | 112 (0.048%) |
| char ≥0.80 OR phon ≥0.90 | 139 (0.059%) |

A consequence SHALL be accepted rather than tuned away: misrenderings that are neither spelt nor pronounced close to the target ("parasite" for "Parakeet") are left uncorrected. That is the ceiling of post-hoc correction.

#### Scenario: Phonetic misrendering corrected
- **WHEN** the output contains a token that is spelt differently from a configured term but reduces to the same sound (e.g. "parakite" against "Parakeet")
- **THEN** the token SHALL be replaced by the configured term

_Tier: unit-pure — `test_text_cleaning.py::TestPhoneticCorrection`. This is the case users reported: character similarity alone scores it 0.750, under the cutoff._

#### Scenario: Ordinary words that merely look similar are left alone
- **WHEN** the output contains a word whose spelling is near a configured term but whose sound is not (e.g. "pense" against "OpenSpec"), or vice versa
- **THEN** the word SHALL be returned unchanged

_Tier: unit-pure — `test_text_cleaning.py::TestPhoneticCorrection`._

#### Scenario: Close variant corrected
- **WHEN** the output contains a token whose similarity to a configured term is above the cutoff (e.g. "wispy" against "Whispy")
- **THEN** the token SHALL be replaced by the configured term

_Tier: unit-pure — `test_text_cleaning.py`._

#### Scenario: Distant token left alone
- **WHEN** the output contains a token whose similarity to every configured term is at or below the cutoff
- **THEN** the token SHALL be returned unchanged

_Tier: unit-pure — `test_text_cleaning.py`._

#### Scenario: No vocabulary term is introduced into unrelated text
- **WHEN** cleaning runs over text containing no near match to any configured term
- **THEN** no configured term SHALL appear in the result

_Tier: unit-pure — `test_text_cleaning.py`._

#### Scenario: Empty vocabulary is a no-op
- **WHEN** `custom_vocabulary` is empty or absent
- **THEN** cleaning SHALL return the input with only whitespace normalization applied

_Tier: unit-pure — `test_text_cleaning.py`._

## REMOVED Requirements

### Requirement: Strip whisper credit prefixes
**Reason**: The credit/watermark phrases were emitted by Whisper. With that backend removed nothing produces them, so the prefix list only retains logic that silently rewrites the user's text.
**Migration**: None. Whitespace normalization stays in `clean_text`.

### Requirement: Strip Whisper hallucination phrases
**Reason**: The blocklist listed Whisper's training-corpus artifacts (`la communauté d'Amara.org`, subtitle credits). Nothing emits those now. Parakeet has its own near-silence failure — short fillers like `Yeah.` / `Okay.` / `Mm-hmm.` — but a blocklist is the wrong instrument for it, because `Okay.` and `No.` are legitimate one-word dictations and filtering by text would delete real speech.
**Migration**: The failure is handled upstream instead, by the RMS silence gate specified in `audio-capture` and `transcription-quality`: near-silent audio never reaches the model, so there is nothing to filter afterwards. Text cleaning no longer inspects transcription content for suppression at all.

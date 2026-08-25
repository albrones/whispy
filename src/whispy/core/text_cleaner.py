"""Text cleaning for transcription output.

Normalizes whitespace and corrects near misses against the user's configured
custom vocabulary.

Whisper-era credit stripping and the hallucination phrase list are gone with the
backend that emitted them. Parakeet's own near-silence failure — short fillers
like "Yeah." or "Okay." — is handled upstream by the RMS gate in ``audio.py``,
not here: those words are legitimate one-word dictations, so suppressing them by
text would delete real speech.
"""

import difflib
import re
import unicodedata

# --- Matching thresholds ----------------------------------------------------
#
# A token is corrected toward a vocabulary term when EITHER its spelling is a
# close match OR it *sounds* the same. Two signals are needed because neither
# alone separates true from false matches.
#
# Character similarity alone cannot: measured against a vocabulary of
# {Whispy, Parakeet, OpenSpec, onnx, Zenika}, a false match outscores a true one.
#
#   wispy    ~ Whispy    0.909   true
#   pense    ~ OpenSpec  0.769   FALSE
#   parakite ~ Parakeet  0.750   true   <- the case that motivated this
#   paraquet ~ Parakeet  0.750   true
#   onyx     ~ onnx      0.750   true
#
# Phonetic similarity separates exactly those: "parakite" and "Parakeet" reduce
# to the same consonant skeleton (1.000) while "pense" ~ "OpenSpec" drops to
# 0.667. But phonetics alone is far too loose — at a 0.80 phonetic cutoff,
# 1763 of 234335 dictionary words match something (0.752%), mangling ordinary
# words like "appreciate". Hence a high phonetic bar plus the character path.
#
# Measured false positives over /usr/share/dict/words (234335 entries, >=4
# letters) against an 8-term vocabulary:
#
#   char >= 0.80 alone                 31  (0.013%)
#   phon >= 0.80 alone               1763  (0.752%)   <- rejected
#   phon >= 0.90 alone                112  (0.048%)
#   char >= 0.80 OR phon >= 0.90      139  (0.059%)   <- shipped
#
# The union costs 4.5x the false positives of characters alone and buys the
# phonetic misrenderings, which are what users actually hit on proper nouns and
# brand names. Distant misses ("parasite" for "Parakeet") stay uncorrected: that
# is the honest ceiling of post-hoc correction, not a bug to tune away.
VOCABULARY_CUTOFF = 0.80
PHONETIC_CUTOFF = 0.90

# Short tokens match short vocabulary terms on coincidence alone ("on" ~ "onnx"
# at 0.667). Skipping them removes that whole class structurally rather than
# hoping the cutoffs catch each case.
MIN_TOKEN_LENGTH = 4

# Leading/trailing punctuation is matched separately so "wispy." can be
# corrected without the period defeating the comparison.
_TOKEN_RE = re.compile(r"^(\W*)(.*?)(\W*)$", re.UNICODE)

# Consonant classes that a French or English speaker renders interchangeably, so
# "parakite"/"parakeet" and "zenica"/"Zenika" collapse to the same key.
_CONSONANT_CLASSES = str.maketrans({"c": "k", "q": "k", "g": "k", "z": "s", "x": "s", "v": "f", "y": "i", "j": "g"})
_DIGRAPHS = (("ph", "f"), ("ck", "k"), ("qu", "k"), ("ch", "x"))


def phonetic_key(word: str) -> str:
    """Reduce a word to a rough consonant skeleton — how it sounds, not how it's spelt.

    Deliberately crude (no Metaphone dependency): strip accents, fold
    interchangeable consonants, drop vowels after the first letter, collapse
    doubles. The first letter is kept because an initial sound is the one part
    speakers rarely get wrong, and dropping it would merge unrelated words.
    """
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    w = re.sub(r"[^a-z]", "", w)
    if not w:
        return ""
    first = w[0]
    for src, dst in _DIGRAPHS:
        w = w.replace(src, dst)
    w = w.translate(_CONSONANT_CLASSES)
    w = re.sub(r"[aeiou]", "", w[1:])
    return re.sub(r"(.)\1+", r"\1", first + w)


def _best_phonetic(core: str, keys: list[str]) -> int | None:
    """Index of the vocabulary term whose sound is closest, if above the cutoff."""
    key = phonetic_key(core)
    if not key:
        return None
    best, best_ratio = None, 0.0
    for i, candidate in enumerate(keys):
        if not candidate:
            continue
        ratio = difflib.SequenceMatcher(None, key, candidate).ratio()
        if ratio > best_ratio:
            best, best_ratio = i, ratio
    return best if best_ratio >= PHONETIC_CUTOFF else None


def _correct_token(token: str, vocabulary: list[str], lowered: list[str], keys: list[str]) -> str:
    """Replace ``token`` with a vocabulary term when spelling or sound matches."""
    prefix, core, suffix = _TOKEN_RE.match(token).groups()
    if len(core) < MIN_TOKEN_LENGTH:
        return token

    matches = difflib.get_close_matches(core.lower(), lowered, n=1, cutoff=VOCABULARY_CUTOFF)
    if matches:
        return prefix + vocabulary[lowered.index(matches[0])] + suffix

    index = _best_phonetic(core, keys)
    if index is not None:
        return prefix + vocabulary[index] + suffix
    return token


def apply_vocabulary(text: str, vocabulary: list[str] | None) -> str:
    """Correct near misses in ``text`` toward the configured ``vocabulary``.

    The transducer backend exposes no decoder-biasing channel, so vocabulary is
    applied after transcription instead of before. A token is corrected when its
    spelling is close to a configured term, or when it sounds like one — the
    latter is what catches "parakite" for "Parakeet", which spelling similarity
    scores below the cutoff.

    Only single tokens are considered — a multi-word vocabulary entry will not
    match, by design, since spanning tokens would make false rewrites likelier.
    """
    if not text or not vocabulary:
        return text
    single = [term for term in vocabulary if term and not term.strip().isspace() and " " not in term.strip()]
    if not single:
        return text
    lowered = [term.lower() for term in single]
    keys = [phonetic_key(term) for term in single]
    return " ".join(_correct_token(tok, single, lowered, keys) for tok in text.split())


def clean_text(text: str | None, vocabulary: list[str] | None = None) -> str | None:
    """Normalize whitespace and apply custom-vocabulary correction.

    Args:
        text: The raw transcribed text, or None.
        vocabulary: Configured ``custom_vocabulary`` terms, or None.

    Returns:
        None if the input is None, otherwise the cleaned text (possibly "").

    Examples:
        >>> clean_text("Hello   world")
        'Hello world'
        >>> clean_text("wispy is great", ["Whispy"])
        'Whispy is great'
        >>> clean_text("le modele parakite", ["Parakeet"])
        'le modele Parakeet'
        >>> clean_text("the cat sat", ["Whispy"])
        'the cat sat'
        >>> clean_text(None) is None
        True
        >>> clean_text("")
        ''
    """
    if text is None:
        return None
    if not text:
        return ""

    cleaned = re.sub(r"\s+", " ", text).strip()
    return apply_vocabulary(cleaned, vocabulary)

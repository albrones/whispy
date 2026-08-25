"""Tests for the text-cleaning module.

Covers whitespace normalization and near-miss correction against the user's
custom vocabulary. The Whisper-era credit and hallucination phrase lists are
gone with the backend that emitted them, and so are their tests.
"""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.text_cleaner import (
    MIN_TOKEN_LENGTH,
    PHONETIC_CUTOFF,
    VOCABULARY_CUTOFF,
    apply_vocabulary,
    clean_text,
    phonetic_key,
)

VOCAB = ["Whispy", "Parakeet", "OpenSpec", "onnx", "Zenika"]


# ---------------------------------------------------------------------------
# Whitespace normalization
# ---------------------------------------------------------------------------


class TestWhitespaceNormalization:
    """clean_text collapses runs of whitespace and trims the edges."""

    def test_runs_collapsed(self):
        assert clean_text("Hello   world") == "Hello world"

    def test_edges_trimmed(self):
        assert clean_text("  hello world  ") == "hello world"

    def test_newlines_and_tabs_collapsed(self):
        assert clean_text("hello\n\tworld") == "hello world"

    def test_plain_text_unchanged(self):
        assert clean_text("Bonjour tout le monde") == "Bonjour tout le monde"

    def test_none_returns_none(self):
        assert clean_text(None) is None

    def test_empty_returns_empty(self):
        assert clean_text("") == ""


# ---------------------------------------------------------------------------
# Near-miss custom vocabulary correction
# ---------------------------------------------------------------------------


class TestVocabularyCorrection:
    """A token close enough to a configured term is replaced by that term."""

    def test_close_variant_corrected(self):
        assert clean_text("wispy is great", VOCAB) == "Whispy is great"

    def test_correction_applies_mid_sentence(self):
        assert clean_text("j'utilise wispy tous les jours", VOCAB) == "j'utilise Whispy tous les jours"

    def test_casing_is_taken_from_the_vocabulary(self):
        assert clean_text("openspec", VOCAB) == "OpenSpec"

    def test_trailing_punctuation_preserved(self):
        assert clean_text("wispy.", VOCAB) == "Whispy."

    def test_leading_and_trailing_punctuation_preserved(self):
        assert clean_text("(wispy)", VOCAB) == "(Whispy)"

    def test_multiple_terms_in_one_sentence(self):
        assert clean_text("openspec, whispy", VOCAB) == "OpenSpec, Whispy"

    def test_already_correct_term_left_alone(self):
        assert clean_text("Whispy is great", VOCAB) == "Whispy is great"


class TestPhoneticCorrection:
    """Terms the model renders phonetically, not orthographically.

    This is the path that catches real user reports: "parakite" for "Parakeet"
    scores only 0.750 on character similarity — below the cutoff — but its
    consonant skeleton is identical.
    """

    def test_phonetic_misrendering_corrected(self):
        assert clean_text("le modele parakite marche", VOCAB) == "le modele Parakeet marche"

    def test_second_phonetic_variant_corrected(self):
        assert clean_text("on utilise paraquet", VOCAB) == "on utilise Parakeet"

    def test_consonant_class_folding(self):
        # y/i, c/k, x/s are interchangeable for a speaker: "onyx" sounds like "onnx".
        assert clean_text("import onyx runtime", VOCAB) == "import onnx runtime"

    def test_accents_are_folded(self):
        assert clean_text("chez zénica", VOCAB) == "chez Zenika"

    def test_phonetic_path_does_not_fire_on_ordinary_words(self):
        # "pense" ~ "OpenSpec" is 0.769 on characters but only 0.667 phonetically:
        # exactly the false positive the phonetic bar is set high enough to reject.
        assert clean_text("je pense que c'est fini", VOCAB) == "je pense que c'est fini"

    def test_english_lookalikes_survive(self):
        for sentence in ("i appreciate that", "an apricot tree", "the parasite spread"):
            assert clean_text(sentence, VOCAB) == sentence


class TestPhoneticKey:
    """The key itself — crude on purpose, no Metaphone dependency."""

    def test_homophone_variants_share_a_key(self):
        assert phonetic_key("parakite") == phonetic_key("parakeet")
        assert phonetic_key("paraquet") == phonetic_key("parakeet")
        assert phonetic_key("zenica") == phonetic_key("zenika")

    def test_unrelated_words_do_not_share_a_key(self):
        assert phonetic_key("pense") != phonetic_key("openspec")
        assert phonetic_key("marche") != phonetic_key("parakeet")

    def test_first_letter_is_preserved(self):
        # Dropping the initial sound would merge unrelated words.
        assert phonetic_key("parakeet").startswith("p")
        assert phonetic_key("whispy").startswith("w")

    def test_accents_and_punctuation_ignored(self):
        assert phonetic_key("Zénika!") == phonetic_key("zenika")

    def test_empty_and_non_alpha_yield_empty(self):
        assert phonetic_key("") == ""
        assert phonetic_key("...") == ""
        assert phonetic_key("1234") == ""


class TestVocabularyLeavesTextAlone:
    """The failure mode that got decoder-prompt biasing removed must not recur."""

    def test_distant_token_not_corrected(self):
        # "pense" ~ "OpenSpec": 0.769 on characters, 0.667 phonetically -- under
        # both bars, which is why neither path fires.
        assert clean_text("je pense que c'est fini", VOCAB) == "je pense que c'est fini"

    def test_short_token_never_matches(self):
        # "on" ~ "onnx" scores 0.667 and is shorter than MIN_TOKEN_LENGTH.
        assert clean_text("on utilise unx runtime", VOCAB) == "on utilise unx runtime"

    def test_unrelated_english_untouched(self):
        assert clean_text("the cat sat on the mat", VOCAB) == "the cat sat on the mat"

    def test_no_vocabulary_term_is_introduced_into_unrelated_text(self):
        corpus = [
            "the cat sat on the mat",
            "je pense que c'est fini",
            "bonjour comment allez vous",
            "on se voit demain matin vers neuf heures",
            "this is a simple sentence about nothing",
        ]
        for sentence in corpus:
            cleaned = clean_text(sentence, VOCAB)
            for term in VOCAB:
                assert term not in cleaned, f"{term!r} injected into {sentence!r} -> {cleaned!r}"


class TestVocabularyEdgeCases:
    """Empty, absent, and unusable vocabularies are no-ops."""

    def test_empty_vocabulary_is_a_noop(self):
        assert clean_text("wispy is great", []) == "wispy is great"

    def test_absent_vocabulary_is_a_noop(self):
        assert clean_text("wispy is great") == "wispy is great"

    def test_multi_word_terms_are_skipped(self):
        # Spanning tokens would make false rewrites likelier, so they are out.
        assert apply_vocabulary("faster whisper", ["faster whisper"]) == "faster whisper"

    def test_multi_word_terms_do_not_disable_single_word_ones(self):
        assert apply_vocabulary("wispy", ["onnx runtime", "Whispy"]) == "Whispy"

    def test_punctuation_only_token_survives(self):
        assert apply_vocabulary("...", VOCAB) == "..."

    def test_empty_text_is_a_noop(self):
        assert apply_vocabulary("", VOCAB) == ""


class TestTuningConstants:
    """The measured constants are part of the contract, not incidental."""

    def test_cutoff_is_strict_enough_to_reject_the_known_false_positive(self):
        import difflib

        ratio = difflib.SequenceMatcher(None, "pense", "openspec").ratio()
        assert ratio < VOCABULARY_CUTOFF, f"'pense'~'openspec' is {ratio:.3f}, cutoff {VOCABULARY_CUTOFF}"

    def test_cutoff_still_accepts_the_known_true_positive(self):
        import difflib

        ratio = difflib.SequenceMatcher(None, "wispy", "whispy").ratio()
        assert ratio >= VOCABULARY_CUTOFF, f"'wispy'~'whispy' is {ratio:.3f}, cutoff {VOCABULARY_CUTOFF}"

    def test_min_token_length_excludes_two_letter_words(self):
        assert MIN_TOKEN_LENGTH > 2

    def test_phonetic_cutoff_is_stricter_than_the_character_cutoff(self):
        """Phonetics is looser by nature, so its bar must be higher.

        At a 0.80 phonetic cutoff, 1763 of 234335 dictionary words matched
        something — ordinary words like "appreciate" would be mangled. 0.90
        brings that to 112.
        """
        assert PHONETIC_CUTOFF > VOCABULARY_CUTOFF

    def test_phonetic_cutoff_still_accepts_the_motivating_case(self):
        import difflib

        ratio = difflib.SequenceMatcher(None, phonetic_key("parakite"), phonetic_key("parakeet")).ratio()
        assert ratio >= PHONETIC_CUTOFF, f"'parakite'~'parakeet' is {ratio:.3f}, cutoff {PHONETIC_CUTOFF}"

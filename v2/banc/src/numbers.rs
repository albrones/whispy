//! The number clips of the reference set: V2's own text must carry the digits.
//!
//! The word error rate reads numbers in digits on both sides ([`crate::wer`]),
//! so it cannot tell that the inverse text normalisation stopped converting.
//! This check reads V2's text as the default configuration produces it (the
//! engine's text through [`whispy_core::itn::normalize`], what the pipeline
//! returns) against digits written here by hand, and the bench exits non-zero
//! when one is missing. The English clip must come out untouched.

use whispy_core::itn;
use whispy_core::{EngineKind, Strategy};

use crate::corpus::Clip;
use crate::measure::Runs;

/// Reference clip id, the digit runs its text must hold (French clips), or
/// none for an English clip, whose text the normalisation must leave alone.
const CASES: &[(&str, &[&str])] = &[
    ("fr-sentence-numbers-rdv", &["3", "2", "12", "14", "30"]),
    ("fr-sentence-numbers-annee", &["2026", "10"]),
    ("fr-short-numbers-compose", &["97"]),
    ("fr-sentence-numbers-un-peu", &["70", "2", "3"]),
    ("en-sentence-numbers", &[]),
];

/// The maximal runs of digits of `text`.
fn digit_runs(text: &str) -> Vec<String> {
    text.split(|c: char| !c.is_ascii_digit())
        .filter(|run| !run.is_empty())
        .map(str::to_string)
        .collect()
}

/// What is wrong with V2's `text` on the clip `id`; `None` when it is right.
fn problem(id: &str, expected: &[&str], text: &str) -> Option<String> {
    let text = itn::normalize(text);
    if id.starts_with("en-") {
        let changed = itn::normalize(&text) != text || !digit_runs(&text).is_empty();
        return changed.then(|| format!("{id}: English text got digits: {text:?}"));
    }
    let mut runs = digit_runs(&text);
    let missing: Vec<&&str> = expected
        .iter()
        .filter(|digits| match runs.iter().position(|run| run == **digits) {
            Some(at) => {
                runs.remove(at);
                false
            }
            None => true,
        })
        .collect();
    (!missing.is_empty()).then(|| format!("{id}: missing {missing:?} in {text:?}"))
}

/// The problems of the number clips in the default configuration's run.
pub fn problems(
    clips: &[Clip],
    runs: &Runs,
    engine: EngineKind,
    strategy: Strategy,
) -> Vec<String> {
    let Some(measured) = runs.get(&(engine, strategy)) else {
        return vec!["no run for the default configuration".to_string()];
    };
    CASES
        .iter()
        .filter_map(|(id, expected)| {
            let Some(index) = clips.iter().position(|clip| clip.id == *id) else {
                return Some(format!("{id}: clip missing from the corpus"));
            };
            problem(id, expected, &measured[index].text)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn digits_are_found_whatever_the_engine_wrote() {
        assert_eq!(
            problem(
                "fr-sentence-numbers-rdv",
                &["3", "2", "12", "14", "30"],
                "Ajoutez trois tests sous deux secondes le 12 décembre à 14h30."
            ),
            None
        );
    }

    #[test]
    fn a_number_left_in_letters_is_a_problem() {
        let text = "ajouter trois tests sous deux secondes le douze décembre";
        // Through the normalisation these come out in digits: no problem.
        assert_eq!(
            problem("fr-short-numbers-compose", &["97"], "quatre-vingt-dix-sept"),
            None
        );
        // A text with no number in it is caught.
        assert!(problem("fr-short-numbers-compose", &["97"], "quatre vingt euh").is_some());
        assert!(problem("fr-sentence-numbers-rdv", &["99"], text).is_some());
    }

    #[test]
    fn english_must_stay_in_letters() {
        assert_eq!(
            problem(
                "en-sentence-numbers",
                &[],
                "I will buy three apples and six eggs"
            ),
            None
        );
        assert!(problem("en-sentence-numbers", &[], "I will buy 3 apples").is_some());
    }
}

//! Word error rate on normalized words.

/// Lowercase words without punctuation; apostrophes and hyphens split words
/// ("l'équipe" and "l' équipe" both read as "l équipe").
pub fn normalized_words(text: &str) -> Vec<String> {
    let spaced: String = text
        .to_lowercase()
        .chars()
        .map(|c| match c {
            '\'' | '\u{2019}' | '\u{2018}' | '-' | '\u{2011}' => ' ',
            c if c.is_alphanumeric() || c.is_whitespace() => c,
            _ => ' ',
        })
        .collect();
    spaced.split_whitespace().map(str::to_string).collect()
}

/// Word-level edit distance (substitutions + insertions + deletions).
pub fn word_edits(expected: &[String], actual: &[String]) -> usize {
    let mut previous: Vec<usize> = (0..=actual.len()).collect();
    for (i, expected_word) in expected.iter().enumerate() {
        let mut current = vec![i + 1; actual.len() + 1];
        for (j, actual_word) in actual.iter().enumerate() {
            let substitution = previous[j] + usize::from(expected_word != actual_word);
            current[j + 1] = substitution.min(previous[j + 1] + 1).min(current[j] + 1);
        }
        previous = current;
    }
    previous[actual.len()]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalization_ignores_case_punctuation_and_apostrophes() {
        assert_eq!(
            normalized_words("À améliorer, je pense."),
            vec!["à", "améliorer", "je", "pense"]
        );
        assert_eq!(normalized_words("l'équipe"), normalized_words("L’ équipe"));
    }

    #[test]
    fn edits_count_each_kind_of_error() {
        let expected = normalized_words("à améliorer je pense");
        assert_eq!(word_edits(&expected, &expected), 0);
        assert_eq!(
            word_edits(&expected, &normalized_words("améliorer je pense")),
            1
        );
        assert_eq!(
            word_edits(&expected, &normalized_words("à améliorer je le pense")),
            1
        );
        assert_eq!(
            word_edits(&expected, &normalized_words("a améliorer je pense")),
            1
        );
        assert_eq!(word_edits(&expected, &[]), 4);
    }
}

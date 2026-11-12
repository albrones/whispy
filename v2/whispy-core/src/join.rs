//! Joining the texts of pieces typed one after another (V1's `join_chunk`,
//! `core/text_cleaner.py`).
//!
//! Each piece is its own model call, which punctuates and capitalizes it as a
//! sentence. A piece cut by the length limit ends mid-sentence, and a bare
//! space would type it as two: « …des tickets. Des tickets qui… ». Typing is
//! append-only, so the decision is taken before each piece is typed: a piece
//! cut mid-speech keeps back its final period, and the next piece follows it
//! with « , » and a lowercase first letter.

/// Joins pieces in typing order. A piece without text is never passed in, so
/// it cannot change how the next one joins.
#[derive(Debug, Default)]
pub struct PieceJoiner {
    has_typed: bool,
    has_withheld_period: bool,
}

impl PieceJoiner {
    /// `text` (one piece's transcript) as it should be typed after the pieces
    /// before it. `is_cut_mid_speech`: the piece was cut by the length limit.
    pub fn next(&mut self, text: &str, is_cut_mid_speech: bool) -> String {
        let text = text.trim();
        let prefix_and_text = if !self.has_typed {
            text.to_string()
        } else if self.has_withheld_period {
            format!(", {}", lowercase_first(text))
        } else {
            format!(" {text}")
        };
        self.has_typed = true;
        let (joined, is_withheld) = if is_cut_mid_speech {
            withhold_period(&prefix_and_text)
        } else {
            (prefix_and_text, false)
        };
        self.has_withheld_period = is_withheld;
        joined
    }

    /// What closes the dictation when its last piece had no text: the period
    /// the piece before kept back, if any.
    pub fn end(&mut self) -> &'static str {
        if std::mem::take(&mut self.has_withheld_period) {
            "."
        } else {
            ""
        }
    }
}

/// Drops a lone trailing `.` (never `?`, `!` or an ellipsis: a wrongly kept
/// question mark is repairable by eye, a wrongly dropped one is not).
fn withhold_period(text: &str) -> (String, bool) {
    match text.strip_suffix('.') {
        Some(kept) if !kept.ends_with('.') => (kept.to_string(), true),
        _ => (text.to_string(), false),
    }
}

/// Lowers the first letter, unless the first word is an acronym (all its
/// letters uppercase, « I » and « À » included) or holds no letter, as V1 does.
// ponytail: V1 also keeps a word of the user's vocabulary capitalized; V2
// has no vocabulary, so a proper noun opening a piece is lowered (V1's
// documented ceiling too).
fn lowercase_first(text: &str) -> String {
    let first_word = text.split(' ').next().unwrap_or_default();
    let core = first_word.trim_matches(|c: char| !c.is_alphanumeric());
    let is_acronym = core.chars().any(char::is_uppercase) && !core.chars().any(char::is_lowercase);
    if core.is_empty() || is_acronym {
        return text.to_string();
    }
    let mut chars = text.chars();
    match chars.next() {
        Some(first) => first.to_lowercase().chain(chars).collect(),
        None => String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pauses_join_with_a_space_and_keep_the_punctuation() {
        let mut joiner = PieceJoiner::default();
        assert_eq!(joiner.next(" Bonjour. ", false), "Bonjour.");
        assert_eq!(joiner.next("Ça va ?", false), " Ça va ?");
        assert_eq!(joiner.end(), "");
    }

    #[test]
    fn a_cut_mid_sentence_rejoins_the_next_piece() {
        let mut joiner = PieceJoiner::default();
        assert_eq!(
            joiner.next("Il y a des tickets.", true),
            "Il y a des tickets"
        );
        assert_eq!(joiner.next("Qui se baladent.", false), ", qui se baladent.");
        // An acronym keeps its capitals; a ? is never withheld.
        assert_eq!(joiner.next("On pousse sur la.", true), " On pousse sur la");
        assert_eq!(joiner.next("API demain ?", true), ", API demain ?");
        assert_eq!(joiner.next("Ensuite.", false), " Ensuite.");
    }

    #[test]
    fn a_withheld_period_comes_back_at_the_end() {
        let mut joiner = PieceJoiner::default();
        assert_eq!(joiner.next("Une phrase coupée.", true), "Une phrase coupée");
        assert_eq!(joiner.end(), ".");
        assert_eq!(
            withhold_period("Attends..."),
            ("Attends...".to_string(), false)
        );
    }
}

//! French inverse text normalisation: spoken numbers written in digits.
//!
//! Parakeet writes numbers in words (« quatorze heures trente »). [`normalize`]
//! rewrites them: cardinals and their compounds (« quatre-vingt-dix-sept » →
//! 97, « deux mille vingt-six » → 2026), hours (« quatorze heures trente » →
//! « 14 h 30 »), percentages (« dix pour cent » → « 10 % »). « un » and « une »
//! stay in letters (an article as often as a number: « un peu », « une fois »)
//! unless they end a compound (« vingt et un » → 21).
//!
//! No language is passed in: only French number words trigger anything, so
//! English text goes through untouched. The words English shares with
//! French, « six », « sept » and « cent », convert only next to no English function word
//! (see [`ENGLISH_WORDS`]).
//!
//! The rolling dictation types text in passages, and a number must never be
//! split between two of them. [`stable_prefix_len`] says how much of the text so
//! far can be typed for good: the trailing number, or a word that may continue
//! one (« et », « pour »), is held back. For any text, normalising the stable
//! prefix gives the start of normalising the whole.

/// English words that mark an English sentence around a lone « six », « sept » or « cent ».
/// None of them is a French word.
const ENGLISH_WORDS: &[&str] = &[
    "the", "of", "and", "to", "is", "are", "was", "were", "with", "for", "you", "your", "we", "i",
    "it", "this", "that", "have", "has", "had", "in", "at", "by", "from", "my", "our", "his",
    "her", "their", "about", "will", "would", "be", "been", "not", "or", "but", "than", "only",
    "just", "over", "under", "more", "less", "last", "next", "all", "any", "some",
];

/// `text` with its spoken numbers in digits. Idempotent; spacing is kept.
pub fn normalize(text: &str) -> String {
    let items = items(text);
    let mut out: Vec<String> = Vec::with_capacity(items.len());
    let mut i = 0;
    while i < items.len() {
        match span_at(&items, i) {
            Some(span) => {
                out.push(span.text);
                i = span.end;
            }
            None => {
                out.push(items[i].text.clone());
                i += 1;
            }
        }
    }
    out.join(" ")
}

/// Bytes of `text` (a whole-token prefix, without its trailing space) that
/// can be typed for good: what remains after it is a number being spoken, or a
/// word that may continue one. `text.len()` when nothing is held.
pub fn stable_prefix_len(text: &str) -> usize {
    let items = items(text);
    let Some(last) = items.len().checked_sub(1) else {
        return text.len();
    };
    let mut last_span: Option<Span> = None;
    let mut i = 0;
    while i < items.len() {
        match span_at(&items, i) {
            Some(span) => {
                i = span.end;
                last_span = Some(span);
            }
            None => i += 1,
        }
    }
    let Some(span) = last_span else {
        return text.len();
    };
    let can_continue = !span.closed
        && (span.end == items.len()
            || (span.end == last && is_continuer(&parse(&items[last].text))));
    if !can_continue {
        return text.len();
    }
    // The token before the held ones is followed by a space we drop.
    items[span.start].start.saturating_sub(1)
}

/// A word that, after a number, may start what the number is part of.
fn is_continuer(token: &Parsed) -> bool {
    token.lead.is_empty() && token.trail.is_empty() && matches!(token.core.as_str(), "et" | "pour")
}

struct Item {
    text: String,
    /// Byte offset of the item's first character in the original text.
    start: usize,
}

/// The space-separated tokens of `text`. A token starting with a hyphen that
/// carries on a number word (« quatre-vingt » « -dix ») is glued to it.
fn items(text: &str) -> Vec<Item> {
    let mut items: Vec<Item> = Vec::new();
    let mut offset = 0;
    for token in text.split(' ') {
        let start = offset;
        offset += token.len() + 1;
        if let (Some(rest), Some(previous)) = (token.strip_prefix('-'), items.last_mut()) {
            if !rest.is_empty()
                && is_number_token(&previous.text, false)
                && is_number_token(rest, true)
            {
                previous.text.push_str(token);
                continue;
            }
        }
        items.push(Item {
            text: token.to_string(),
            start,
        });
    }
    items
}

/// Whether every hyphen-separated part of the token's word is a number word.
fn is_number_token(token: &str, allow_trail: bool) -> bool {
    let parsed = parse(token);
    (allow_trail || parsed.trail.is_empty())
        && !parsed.core.is_empty()
        && parsed
            .core
            .split('-')
            .all(|part| part == "et" || atom(part).is_some())
}

struct Parsed {
    /// Punctuation before the word (« ( », « « »).
    lead: String,
    /// The word, lowercase; letters, digits, inner hyphens and apostrophes.
    core: String,
    /// Punctuation after the word.
    trail: String,
}

fn parse(token: &str) -> Parsed {
    let core_start = token
        .char_indices()
        .find(|(_, c)| c.is_alphanumeric())
        .map_or(token.len(), |(i, _)| i);
    let core_end = token
        .char_indices()
        .rev()
        .find(|(_, c)| c.is_alphanumeric())
        .map_or(core_start, |(i, c)| i + c.len_utf8());
    Parsed {
        lead: token[..core_start].to_string(),
        core: token[core_start..core_end].to_lowercase(),
        trail: token[core_end..].to_string(),
    }
}

#[derive(Clone, Copy, PartialEq)]
enum Atom {
    Zero,
    /// 1..=99: units, teens, tens.
    Small(u32),
    Hundred,
    Thousand,
}

fn atom(word: &str) -> Option<Atom> {
    Some(match word {
        "zéro" => Atom::Zero,
        "un" | "une" => Atom::Small(1),
        "deux" => Atom::Small(2),
        "trois" => Atom::Small(3),
        "quatre" => Atom::Small(4),
        "cinq" => Atom::Small(5),
        "six" => Atom::Small(6),
        "sept" => Atom::Small(7),
        "huit" => Atom::Small(8),
        "neuf" => Atom::Small(9),
        "dix" => Atom::Small(10),
        "onze" => Atom::Small(11),
        "douze" => Atom::Small(12),
        "treize" => Atom::Small(13),
        "quatorze" => Atom::Small(14),
        "quinze" => Atom::Small(15),
        "seize" => Atom::Small(16),
        "vingt" | "vingts" => Atom::Small(20),
        "trente" => Atom::Small(30),
        "quarante" => Atom::Small(40),
        "cinquante" => Atom::Small(50),
        "soixante" => Atom::Small(60),
        "septante" => Atom::Small(70),
        "huitante" | "octante" => Atom::Small(80),
        "nonante" => Atom::Small(90),
        "cent" | "cents" => Atom::Hundred,
        "mille" => Atom::Thousand,
        _ => return None,
    })
}

/// A number being read word by word.
#[derive(Clone, Default)]
struct Acc {
    thousands: u32,
    hundreds: u32,
    rest: u32,
    used_thousand: bool,
    zero: bool,
    atoms: usize,
    /// Every atom so far is « six », « sept » or « cent »: English has them too.
    only_shared: bool,
    /// The last atom was « quatre » (« quatre-vingt »).
    after_four: bool,
    /// The only atom so far is « un » or « une ».
    only_un: bool,
}

impl Acc {
    fn new() -> Acc {
        Acc {
            only_shared: true,
            only_un: true,
            ..Acc::default()
        }
    }

    fn value(&self) -> u32 {
        self.thousands * 1000 + self.hundreds + self.rest
    }

    /// Whether « et » may come now, before `next`.
    fn can_et(&self, next: &str) -> bool {
        match next {
            "un" | "une" => matches!(self.rest, 20 | 30 | 40 | 50),
            "onze" => self.rest == 60,
            _ => false,
        }
    }

    /// Adds the word; `false` (and the accumulator is then useless) when it
    /// cannot follow what is read.
    fn push(&mut self, word: &str) -> bool {
        let Some(atom) = atom(word) else {
            return false;
        };
        if self.zero {
            return false;
        }
        let is_four = word == "quatre";
        let ok = match atom {
            Atom::Zero => {
                self.zero = self.atoms == 0;
                self.zero
            }
            Atom::Small(v) => self.push_small(v),
            Atom::Hundred => self.push_hundred(),
            Atom::Thousand => self.push_thousand(),
        };
        if ok {
            self.atoms += 1;
            self.only_shared &= matches!(word, "six" | "sept" | "cent" | "cents");
            self.only_un &= matches!(word, "un" | "une") && self.atoms == 1;
            self.after_four = is_four;
        }
        ok
    }

    fn push_small(&mut self, v: u32) -> bool {
        let rest = self.rest;
        if v == 20 && self.after_four && rest == 4 {
            self.rest = 80;
            return true;
        }
        let allowed = match rest {
            0 => true,
            10 => (7..=9).contains(&v),
            20 | 30 | 40 | 50 | 70 | 90 => v < 10,
            60 => v < 20,
            80 => v < 20,
            _ => false,
        };
        if allowed {
            self.rest += v;
        }
        allowed
    }

    fn push_hundred(&mut self) -> bool {
        if self.hundreds > 0 {
            return false;
        }
        match self.rest {
            0 => self.hundreds = 100,
            1..=9 => self.hundreds = self.rest * 100,
            // « dix-neuf cent quatre-vingt »: a year.
            10..=19 if self.thousands == 0 && !self.used_thousand => {
                self.hundreds = self.rest * 100;
            }
            _ => return false,
        }
        self.rest = 0;
        true
    }

    fn push_thousand(&mut self) -> bool {
        if self.used_thousand {
            return false;
        }
        self.thousands = (self.hundreds + self.rest).max(1);
        self.hundreds = 0;
        self.rest = 0;
        self.used_thousand = true;
        true
    }
}

/// A number read from some tokens.
struct Number {
    end: usize,
    value: u32,
    lead: String,
    trail: String,
    only_shared: bool,
}

/// The number that starts at item `start`, as long as the words allow.
fn number_at(items: &[Item], start: usize) -> Option<Number> {
    let mut acc = Acc::new();
    let (mut end, mut k) = (start, start);
    let (mut lead, mut trail) = (String::new(), String::new());
    while k < items.len() {
        let token = parse(&items[k].text);
        if token.core.is_empty() || (k > start && !token.lead.is_empty()) {
            break;
        }
        if token.core == "et" {
            // « vingt et un »: the « et » only counts with the word after it.
            let next = items.get(k + 1).map(|item| parse(&item.text));
            let fits = k > start
                && token.trail.is_empty()
                && next.is_some_and(|next| {
                    next.lead.is_empty()
                        && acc.can_et(next.core.split('-').next().unwrap_or_default())
                });
            if !fits {
                break;
            }
            k += 1;
            continue;
        }
        let mut trial = acc.clone();
        let mut ok = true;
        let parts: Vec<&str> = token.core.split('-').collect();
        for (i, part) in parts.iter().enumerate() {
            if *part == "et" {
                // « vingt-et-un ».
                ok = i > 0 && parts.get(i + 1).is_some_and(|next| trial.can_et(next));
            } else {
                ok = trial.push(part);
            }
            if !ok {
                break;
            }
        }
        if !ok {
            break;
        }
        acc = trial;
        if end == start {
            lead = token.lead.clone();
        }
        end = k + 1;
        trail = token.trail.clone();
        k += 1;
        if !trail.is_empty() {
            break;
        }
    }
    if end == start || acc.only_un {
        return None;
    }
    Some(Number {
        end,
        value: acc.value(),
        lead,
        trail,
        only_shared: acc.only_shared,
    })
}

struct Span {
    start: usize,
    end: usize,
    text: String,
    /// The last token ends on punctuation: nothing can carry the number on.
    closed: bool,
}

/// The rewritten number, with the units it governs, that starts at `start`.
fn span_at(items: &[Item], start: usize) -> Option<Span> {
    let number = number_at(items, start)?;
    let digits = format!("{}{}", number.lead, number.value);
    let after = |offset: usize| items.get(number.end + offset).map(|item| parse(&item.text));
    if number.trail.is_empty() {
        let (first, second) = (after(0), after(1));
        // « dix pour cent ».
        if let (Some(a), Some(b)) = (&first, &second) {
            if is_bare(a, "pour") && b.lead.is_empty() && b.core == "cent" {
                return Some(Span {
                    start,
                    end: number.end + 2,
                    text: format!("{digits} %{}", b.trail),
                    closed: !b.trail.is_empty(),
                });
            }
        }
        // « quatorze heures trente ».
        if let Some(a) = first.filter(|a| a.lead.is_empty() && is_hours(&a.core)) {
            if number.value <= 24 {
                if let Some(span) = hours_at(items, start, &number, &digits, &a) {
                    return Some(span);
                }
            }
            return Some(Span {
                start,
                end: number.end + 1,
                text: format!("{digits} {}", items[number.end].text),
                closed: !a.trail.is_empty(),
            });
        }
    }
    if number.only_shared && is_english_around(items, start, &number) {
        return None;
    }
    Some(Span {
        start,
        end: number.end,
        text: format!("{digits}{}", number.trail),
        closed: !number.trail.is_empty(),
    })
}

fn is_bare(token: &Parsed, word: &str) -> bool {
    token.lead.is_empty() && token.trail.is_empty() && token.core == word
}

fn is_hours(word: &str) -> bool {
    matches!(word, "heure" | "heures")
}

/// « quatorze heures » followed by minutes: « 14 h 30 ».
fn hours_at(
    items: &[Item],
    start: usize,
    hours: &Number,
    digits: &str,
    word: &Parsed,
) -> Option<Span> {
    if !word.trail.is_empty() {
        return None;
    }
    let minutes_at = hours.end + 1;
    let at = |offset: usize| items.get(minutes_at + offset).map(|item| parse(&item.text));
    // « et demie », « et quart ».
    if let (Some(and), Some(fraction)) = (at(0), at(1)) {
        let minutes = match fraction.core.as_str() {
            "demie" | "demi" => Some(30),
            "quart" => Some(15),
            _ => None,
        };
        if let (true, Some(minutes)) = (is_bare(&and, "et") && fraction.lead.is_empty(), minutes) {
            return Some(Span {
                start,
                end: minutes_at + 2,
                text: format!("{digits} h {minutes:02}{}", fraction.trail),
                closed: !fraction.trail.is_empty(),
            });
        }
    }
    let minutes = number_at(items, minutes_at)?;
    if !minutes.lead.is_empty() || !(1..60).contains(&minutes.value) {
        return None;
    }
    Some(Span {
        start,
        end: minutes.end,
        text: format!("{digits} h {:02}{}", minutes.value, minutes.trail),
        closed: !minutes.trail.is_empty(),
    })
}

/// A lone « six » or « cent » beside an English function word, or at the
/// start of the sentence's English: left alone.
fn is_english_around(items: &[Item], start: usize, number: &Number) -> bool {
    let is_english = |item: &Item| ENGLISH_WORDS.contains(&parse(&item.text).core.as_str());
    let before = start.checked_sub(1).and_then(|i| items.get(i));
    let after = items.get(number.end).filter(|_| number.trail.is_empty());
    before.is_some_and(is_english) || after.is_some_and(is_english)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn n(text: &str) -> String {
        normalize(text)
    }

    #[test]
    fn the_parakeet_sentence_of_the_manual_test_comes_out_in_digits() {
        assert_eq!(
            n("ajouter trois tests sous deux secondes le douze décembre à quatorze heures trente"),
            "ajouter 3 tests sous 2 secondes le 12 décembre à 14 h 30"
        );
    }

    #[test]
    fn compounds_and_percentages_come_out_in_digits() {
        for (spoken, digits) in [
            ("soixante-dix", "70"),
            ("quatre-vingt-dix-sept", "97"),
            ("quatre-vingts", "80"),
            ("Quatre-vingt dix sept.", "97."),
            ("quatre vingt dix", "90"),
            ("deux mille vingt-six", "2026"),
            ("vingt et un", "21"),
            ("vingt-et-un", "21"),
            ("soixante et onze", "71"),
            ("soixante-douze", "72"),
            ("dix-sept", "17"),
            ("cent un", "101"),
            ("deux cents", "200"),
            ("trois cent quatre-vingt-quinze", "395"),
            ("mille", "1000"),
            ("mille neuf cent quatre-vingt-dix", "1990"),
            ("dix-neuf cent quatre-vingt-dix", "1990"),
            ("cent mille", "100000"),
            ("zéro", "0"),
            ("dix pour cent", "10 %"),
            ("cent pour cent", "100 %"),
            ("vingt-cinq pour cent.", "25 %."),
            ("Deux mille vingt-six,", "2026,"),
        ] {
            assert_eq!(n(spoken), digits, "{spoken}");
        }
    }

    #[test]
    fn hours_take_their_minutes() {
        assert_eq!(n("à quatorze heures"), "à 14 heures");
        assert_eq!(n("à quatorze heures cinq"), "à 14 h 05");
        assert_eq!(n("à huit heures et demie."), "à 8 h 30.");
        assert_eq!(n("à neuf heures et quart"), "à 9 h 15");
        assert_eq!(n("vingt-quatre heures de route"), "24 heures de route");
        assert_eq!(n("trente heures"), "30 heures");
    }

    #[test]
    fn every_number_but_un_and_une_is_in_digits() {
        assert_eq!(n("deux ou trois choses"), "2 ou 3 choses");
        assert_eq!(n("un deux trois"), "un 2 3");
        assert_eq!(n("(trois) \"quatre\" «cinq»"), "(3) \"4\" «5»");
    }

    #[test]
    fn words_that_do_not_count_stay_in_letters() {
        for text in [
            "un peu",
            "une fois",
            "l'un des",
            "il y en a un",
            "une heure",
            "Un jour, une idée.",
            "deux-points",
        ] {
            assert_eq!(n(text), text, "{text}");
        }
    }

    #[test]
    fn english_is_untouched() {
        for text in [
            "I have six apples",
            "the six of us",
            "one two three, testing",
            "we paid one cent and six more",
            "at eight o'clock sharp",
            "ten per cent of the total",
        ] {
            assert_eq!(n(text), text);
        }
    }

    #[test]
    fn normalizing_twice_changes_nothing() {
        let once = n("à quatorze heures trente, dix pour cent de quatre-vingt-dix-sept");
        assert_eq!(n(&once), once);
    }

    #[test]
    fn spacing_is_kept() {
        assert_eq!(n(" trois  tests "), " 3  tests ");
        assert_eq!(n(""), "");
    }

    #[test]
    fn a_hyphen_cut_between_passages_is_glued() {
        assert_eq!(n("quatre-vingt -dix"), "90");
        assert_eq!(n("a -b"), "a -b");
    }

    /// Types `words` the way the rolling dictation does: the text so far is
    /// released passage by passage, holding the trailing number back.
    fn live(words: &[&str], cuts: &[usize]) -> String {
        let (mut raw, mut shown, mut typed) = (String::new(), String::new(), String::new());
        let mut from = 0;
        for &cut in cuts.iter().chain(std::iter::once(&words.len())) {
            for word in &words[from..cut] {
                if !raw.is_empty() {
                    raw.push(' ');
                }
                raw.push_str(word);
            }
            from = cut;
            let last = cut == words.len();
            let stable = if last {
                raw.len()
            } else {
                stable_prefix_len(&raw)
            };
            let target = normalize(&raw[..stable]);
            let rest = target
                .strip_prefix(shown.as_str())
                .unwrap_or_else(|| panic!("{shown:?} is not a prefix of {target:?}"));
            typed.push_str(rest);
            shown = target;
        }
        typed
    }

    #[test]
    fn typed_in_any_passages_the_text_equals_one_block() {
        for sentence in [
            "ajouter trois tests sous deux secondes le douze décembre à quatorze heures trente",
            "il a quatre-vingt-dix-sept ans et vingt et un jours",
            "rendez-vous à quatorze heures et demie pour dix pour cent",
            "en deux mille vingt-six, soit cent pour cent de soixante-dix",
            "j'ai six chats, vingt-six. Trois, quatre, cinq heures.",
            "un peu de mille et une choses à quatre heures",
            "I have six apples and one cent at eight o'clock",
        ] {
            let words: Vec<&str> = sentence.split(' ').collect();
            let block = normalize(sentence);
            for first in 1..words.len() {
                for second in first..words.len() {
                    assert_eq!(
                        live(&words, &[first, second]),
                        block,
                        "{sentence} cut at {first}, {second}"
                    );
                }
            }
        }
    }

    #[test]
    fn a_number_is_held_until_what_follows_is_known() {
        let held = |text: &str| text[..stable_prefix_len(text)].to_string();
        assert_eq!(held("à quatre-vingt"), "à");
        assert_eq!(held("à quatorze heures"), "à");
        assert_eq!(held("à quatorze heures trente"), "à");
        assert_eq!(held("il a vingt et"), "il a");
        assert_eq!(held("dix pour"), "");
        assert_eq!(held("il a vingt ans"), "il a vingt ans");
        assert_eq!(held("il a vingt,"), "il a vingt,");
        assert_eq!(held("un peu"), "un peu");
        assert_eq!(held(""), "");
        assert_eq!(held(" quatre-vingt"), "");
    }

    #[test]
    fn a_split_hyphen_compound_types_as_one_block() {
        assert_eq!(
            live(&["il", "a", "quatre-vingt", "-dix", "ans"], &[3]),
            "il a 90 ans"
        );
        assert_eq!(
            live(&["à", "quatorze", "heures", "trente"], &[2]),
            "à 14 h 30"
        );
    }
}

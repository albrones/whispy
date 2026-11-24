//! French inverse text normalisation: spoken numbers written in digits.
//!
//! Parakeet writes numbers in words (« quatorze heures trente »). [`normalize`]
//! rewrites them: cardinals and their compounds (« quatre-vingt-dix-sept » →
//! 97, « deux mille vingt-six » → 2026, « deux millions cinq cent mille » →
//! 2500000), hours (« quatorze heures trente », « 14 heures trente », « 14h30 »
//! → « 14 h 30 »), percentages (« dix pour cent » → « 10 % »). « un » and « une »
//! stay in letters (an article as often as a number: « un peu », « une fois »)
//! unless they end a compound (« vingt et un » → 21) or give the hour of
//! « une heure trente » (→ « 1 h 30 »).
//!
//! No language is passed in: only French number words trigger anything, so
//! English text goes through untouched. Words English shares with French
//! (« six », « sept », « cent », « million ») stay in letters only with
//! English around them: an English function word within three words in the
//! same clause (« I will take six. »), or a singular « million » after a number
//! (« six million dollars »). « cents » and « vingts » never start a number,
//! and the adjective « neuf » stays in letters (« un pull neuf », « du neuf »,
//! « tout neuf », « quoi de neuf ? »).
//!
//! The rolling dictation types text in passages, and a number must never be
//! split between two of them. [`stable_prefix_len`] says how much of the text so
//! far can be typed for good: whatever could still become part of a number is
//! held back, even a number a guard would reject now. For any text, normalising
//! the stable prefix gives the start of normalising the whole.

/// English words that mark English around a number shared with French. None
/// of them is a French word.
const ENGLISH_WORDS: &[&str] = &[
    "the", "of", "and", "to", "is", "are", "was", "were", "with", "for", "you", "your", "we", "i",
    "it", "this", "that", "have", "has", "had", "in", "at", "by", "from", "my", "our", "his",
    "her", "their", "about", "will", "would", "be", "been", "not", "but", "than", "only", "just",
    "over", "under", "more", "less", "last", "next", "all", "any", "some", "one", "two", "three",
    "four", "five", "eight", "nine", "ten", "twenty", "thirty", "forty", "fifty", "sixty",
    "seventy", "eighty", "ninety", "hundred", "thousand",
];

/// Words around which a lone « neuf » is read as the number: articles, so that
/// « un pull neuf » (article, noun, « neuf ») is the adjective.
const ARTICLES: &[&str] = &[
    "un", "une", "le", "la", "les", "des", "ce", "cette", "ces", "mon", "ma", "mes", "ton", "ta",
    "tes", "son", "sa", "ses", "notre", "votre", "leur", "leurs",
];

/// Tokens looked at on each side of a number shared with English.
const ENGLISH_WINDOW: usize = 3;

/// `text` with its spoken numbers in digits. Idempotent; spacing is kept.
pub fn normalize(text: &str) -> String {
    let items = items(text);
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < items.len() {
        if let Some(separator) = items[i].before {
            out.push(separator);
        }
        match span_at(&items, i, true) {
            Some(span) => {
                out.push_str(&span.text);
                i = span.end;
            }
            None => {
                out.push_str(&items[i].text);
                i += 1;
            }
        }
    }
    out
}

/// Bytes of `text` (a whole-token prefix, without its trailing separator) that
/// can be typed for good: what remains after it is a number being spoken, or a
/// word that may continue one. `text.len()` when nothing is held.
pub fn stable_prefix_len(text: &str) -> usize {
    let items = items(text);
    let Some(last) = items.len().checked_sub(1) else {
        return text.len();
    };
    let mut spans: Vec<Span> = Vec::new();
    let mut i = 0;
    while i < items.len() {
        match span_at(&items, i, false) {
            Some(span) => {
                i = span.end;
                spans.push(span);
            }
            None => i += 1,
        }
    }
    let mut held: Option<usize> = None;
    // A number shared with English waits for the words that decide it.
    for span in spans.iter().filter(|span| span.ambiguous && !span.closed) {
        if !clause_window_is_complete(&items[span.end..]) {
            held = Some(held.map_or(span.start, |h| h.min(span.start)));
        }
    }
    if let Some(span) = spans.last() {
        let can_continue = !span.closed
            && (span.end == items.len()
                || (span.end == last && is_continuer(&parse(&items[last].text))));
        if can_continue {
            held = Some(held.map_or(span.start, |h| h.min(span.start)));
        }
    }
    let tail = parse(&items[last].text);
    if tail.trail.is_empty() && tail.lead.is_empty() {
        // A lone « un » / « une » may be the hour of « une heure trente »;
        // digits may be followed by « heures » or « pour cent ».
        let after_digits = last
            .checked_sub(1)
            .is_some_and(|k| digits_at(&items, k).is_some_and(|d| d.trail.is_empty()));
        let is_digits = digits_at(&items, last).is_some();
        if is_digits
            || matches!(tail.core.as_str(), "un" | "une")
            || (tail.core == "pour" && after_digits)
        {
            let from = if tail.core == "pour" { last - 1 } else { last };
            held = Some(held.map_or(from, |h| h.min(from)));
        }
    }
    match held {
        Some(h) => items[h].start - items[h].before.map_or(0, char::len_utf8),
        None => text.len(),
    }
}

/// A word that, after a number, may start what the number is part of.
fn is_continuer(token: &Parsed) -> bool {
    token.lead.is_empty() && token.trail.is_empty() && matches!(token.core.as_str(), "et" | "pour")
}

struct Item {
    text: String,
    /// Byte offset of the item's first character in the original text.
    start: usize,
    /// The whitespace character before it, `None` for the first item.
    before: Option<char>,
}

/// The whitespace-separated tokens of `text` (every whitespace character
/// separates and is kept; two in a row leave an empty token between). A token
/// starting with a hyphen that carries on a number word (« quatre-vingt »
/// « -dix ») is glued to it.
fn items(text: &str) -> Vec<Item> {
    let mut items: Vec<Item> = Vec::new();
    let mut before = None;
    let mut start = 0;
    let mut tokens: Vec<(usize, &str, Option<char>)> = Vec::new();
    for (i, c) in text.char_indices() {
        if c.is_whitespace() {
            tokens.push((start, &text[start..i], before));
            before = Some(c);
            start = i + c.len_utf8();
        }
    }
    tokens.push((start, &text[start..], before));
    for (start, token, before) in tokens {
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
            before,
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
    Small(u64),
    Hundred,
    Thousand,
    /// « million », « milliard ».
    Scale(u64),
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
        "million" | "millions" => Atom::Scale(1_000_000),
        "milliard" | "milliards" => Atom::Scale(1_000_000_000),
        _ => return None,
    })
}

/// A number being read word by word.
#[derive(Clone)]
struct Acc {
    big: u64,
    /// The last scale used (« million »), words of a smaller one may follow.
    last_scale: u64,
    thousands: u64,
    hundreds: u64,
    rest: u64,
    used_thousand: bool,
    zero: bool,
    atoms: usize,
    /// Every atom so far is « six », « sept », « cent » or « million »: English has them too.
    only_shared: bool,
    /// The last atom was « quatre » (« quatre-vingt »).
    after_four: bool,
    /// The only atom so far is « un » or « une ».
    only_un: bool,
    /// A singular « million » followed a number above one.
    english: bool,
}

impl Acc {
    fn new() -> Acc {
        Acc {
            big: 0,
            last_scale: u64::MAX,
            thousands: 0,
            hundreds: 0,
            rest: 0,
            used_thousand: false,
            zero: false,
            atoms: 0,
            only_shared: true,
            after_four: false,
            only_un: true,
            english: false,
        }
    }

    fn group(&self) -> u64 {
        self.thousands * 1000 + self.hundreds + self.rest
    }

    fn value(&self) -> u64 {
        self.big + self.group()
    }

    /// Whether « et » may come now, before `next`.
    fn can_et(&self, next: &str) -> bool {
        match next {
            "un" | "une" => {
                matches!(self.rest, 20 | 30 | 40 | 50)
                    || (self.used_thousand && self.hundreds == 0 && self.rest == 0)
            }
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
            Atom::Scale(scale) => self.push_scale(scale, word.ends_with('s')),
        };
        if ok {
            self.atoms += 1;
            self.only_shared &= matches!(
                word,
                "six" | "sept" | "cent" | "cents" | "million" | "millions"
            );
            self.only_un &= matches!(word, "un" | "une") && self.atoms == 1;
            self.after_four = is_four;
        }
        ok
    }

    fn push_small(&mut self, v: u64) -> bool {
        let rest = self.rest;
        if v == 20 && self.after_four && rest == 4 {
            self.rest = 80;
            return true;
        }
        let allowed = match rest {
            0 => true,
            10 => (7..=9).contains(&v),
            20 | 30 | 40 | 50 | 70 | 90 => v < 10,
            60 | 80 => v < 20,
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
            10..=19 if self.big == 0 && self.thousands == 0 && !self.used_thousand => {
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

    fn push_scale(&mut self, scale: u64, is_plural: bool) -> bool {
        let group = self.group();
        self.english |= !is_plural && group > 1;
        if group == 0 || scale >= self.last_scale {
            return false;
        }
        self.big += group * scale;
        self.thousands = 0;
        self.hundreds = 0;
        self.rest = 0;
        self.used_thousand = false;
        self.last_scale = scale;
        true
    }
}

#[derive(Clone, Copy, PartialEq)]
enum Source {
    /// Number words.
    Words,
    /// Digits the engine wrote itself.
    Digits,
    /// « une », only as the hour of « une heure trente ».
    Une,
}

/// A number read from some tokens.
struct Number {
    source: Source,
    end: usize,
    value: u64,
    /// The number as it is written: punctuation before, then digits.
    shown: String,
    trail: String,
    only_shared: bool,
    /// The only word of a number made of words.
    lone: Option<String>,
    /// A singular « million » after a number: English (« six million »).
    english: bool,
}

/// The number that starts at item `start`, as long as the words allow.
fn number_at(items: &[Item], start: usize) -> Option<Number> {
    let mut acc = Acc::new();
    let (mut end, mut k) = (start, start);
    let (mut lead, mut trail) = (String::new(), String::new());
    let mut first_word = String::new();
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
            first_word = parts[0].to_string();
        }
        end = k + 1;
        trail = token.trail.clone();
        k += 1;
        if !trail.is_empty() {
            break;
        }
    }
    // « cents » and « vingts » only end a number; « un » alone is no number.
    if end == start || acc.only_un || matches!(first_word.as_str(), "cents" | "vingts") {
        return None;
    }
    Some(Number {
        source: Source::Words,
        end,
        value: acc.value(),
        shown: format!("{lead}{}", acc.value()),
        trail,
        only_shared: acc.only_shared,
        lone: (acc.atoms == 1).then_some(first_word),
        english: acc.english,
    })
}

/// Digits the engine wrote (« 14 »), as a number for the units after it.
fn digits_at(items: &[Item], start: usize) -> Option<Number> {
    let token = parse(&items.get(start)?.text);
    if token.core.is_empty()
        || token.core.len() > 9
        || !token.core.bytes().all(|b| b.is_ascii_digit())
    {
        return None;
    }
    Some(Number {
        source: Source::Digits,
        end: start + 1,
        value: token.core.parse().ok()?,
        shown: format!("{}{}", token.lead, token.core),
        trail: token.trail,
        only_shared: false,
        lone: None,
        english: false,
    })
}

/// « une » before « heure » (« une heure trente »).
fn une_at(items: &[Item], start: usize) -> Option<Number> {
    let token = parse(&items.get(start)?.text);
    let next = parse(&items.get(start + 1)?.text);
    (token.core == "une" && token.trail.is_empty() && next.lead.is_empty() && is_hours(&next.core))
        .then(|| Number {
            source: Source::Une,
            end: start + 1,
            value: 1,
            shown: format!("{}1", token.lead),
            trail: String::new(),
            only_shared: false,
            lone: None,
            english: false,
        })
}

struct Span {
    start: usize,
    end: usize,
    text: String,
    /// The last token ends on punctuation: nothing can carry the number on.
    closed: bool,
    /// Made of words English shares (« six »): English around it keeps it in letters.
    ambiguous: bool,
}

/// The rewritten number, with the units it governs, that starts at `start`.
/// Not `strict`, the guards that leave a number in letters are off and a
/// number that only gets digits when something follows is still a span: that
/// is what [`stable_prefix_len`] holds back.
fn span_at(items: &[Item], start: usize, strict: bool) -> Option<Span> {
    if let Some(span) = clock_at(items, start) {
        return Some(span);
    }
    let number = number_at(items, start)
        .or_else(|| digits_at(items, start))
        .or_else(|| une_at(items, start))?;
    // « 10% », as Parakeet writes it.
    if number.source == Source::Digits && number.trail.starts_with('%') {
        return Some(Span {
            start,
            end: number.end,
            text: format!("{} {}", number.shown, number.trail),
            closed: true,
            ambiguous: false,
        });
    }
    if number.trail.is_empty() {
        if let Some(span) = unit_span(items, start, &number, strict) {
            return Some(span);
        }
    }
    if number.source != Source::Words || (strict && is_left_in_letters(items, start, &number)) {
        return None;
    }
    Some(Span {
        start,
        end: number.end,
        text: format!("{}{}", number.shown, number.trail),
        closed: !number.trail.is_empty(),
        ambiguous: number.only_shared,
    })
}

/// « 14h30 », as Parakeet writes it.
fn clock_at(items: &[Item], start: usize) -> Option<Span> {
    let token = parse(&items.get(start)?.text);
    let (hours, minutes) = token.core.split_once('h')?;
    let digits = |s: &str, n: usize| s.len() <= n && s.bytes().all(|b| b.is_ascii_digit());
    if hours.is_empty() || minutes.len() != 2 || !digits(hours, 2) || !digits(minutes, 2) {
        return None;
    }
    if hours.parse::<u32>().ok()? > 24 || minutes.parse::<u32>().ok()? > 59 {
        return None;
    }
    Some(Span {
        start,
        end: start + 1,
        text: format!("{}{hours} h {minutes}{}", token.lead, token.trail),
        closed: !token.trail.is_empty(),
        ambiguous: false,
    })
}

/// « pour cent » and « heures » after a number.
fn unit_span(items: &[Item], start: usize, number: &Number, strict: bool) -> Option<Span> {
    let after = |offset: usize| items.get(number.end + offset).map(|item| parse(&item.text));
    let (first, second) = (after(0), after(1));
    // « dix pour cent ».
    if let (Some(a), Some(b)) = (&first, &second) {
        if number.source != Source::Une
            && is_bare(a, "pour")
            && b.lead.is_empty()
            && b.core == "cent"
        {
            return Some(Span {
                start,
                end: number.end + 2,
                text: format!("{} %{}", number.shown, b.trail),
                closed: !b.trail.is_empty(),
                ambiguous: false,
            });
        }
    }
    // « quatorze heures trente ».
    let a = first.filter(|a| a.lead.is_empty() && is_hours(&a.core))?;
    if number.value > 24 {
        return None;
    }
    if let Some(span) = hours_at(items, start, number, &a) {
        return Some(span);
    }
    if number.source == Source::Une && strict {
        return None;
    }
    Some(Span {
        start,
        end: number.end + 1,
        text: format!(
            "{} {}",
            if number.source == Source::Une {
                items[start].text.clone()
            } else {
                number.shown.clone()
            },
            items[number.end].text
        ),
        closed: !a.trail.is_empty(),
        ambiguous: false,
    })
}

fn is_bare(token: &Parsed, word: &str) -> bool {
    token.lead.is_empty() && token.trail.is_empty() && token.core == word
}

fn is_hours(word: &str) -> bool {
    matches!(word, "heure" | "heures")
}

/// « quatorze heures » followed by minutes: « 14 h 30 ».
fn hours_at(items: &[Item], start: usize, hours: &Number, word: &Parsed) -> Option<Span> {
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
                text: format!("{} h {minutes:02}{}", hours.shown, fraction.trail),
                closed: !fraction.trail.is_empty(),
                ambiguous: false,
            });
        }
    }
    let minutes = number_at(items, minutes_at).or_else(|| digits_at(items, minutes_at))?;
    let lead_free = items[minutes_at]
        .text
        .starts_with(|c: char| c.is_alphanumeric());
    if !lead_free || !(1..60).contains(&minutes.value) {
        return None;
    }
    Some(Span {
        start,
        end: minutes.end,
        text: format!("{} h {:02}{}", hours.shown, minutes.value, minutes.trail),
        closed: !minutes.trail.is_empty(),
        ambiguous: false,
    })
}

/// A number made of words that stays in letters: one with English around it
/// when made of words English shares, a singular « million » after a number
/// (English), and the adjective « neuf ».
fn is_left_in_letters(items: &[Item], start: usize, number: &Number) -> bool {
    if number.english {
        return true;
    }
    if number.only_shared && has_english_around(items, start, number) {
        return true;
    }
    number.lone.as_deref() == Some("neuf") && is_adjective_neuf(items, start, number)
}

/// An English function word within [`ENGLISH_WINDOW`] tokens on either side,
/// in the same clause (a token ending on punctuation closes it).
fn has_english_around(items: &[Item], start: usize, number: &Number) -> bool {
    let is_english = |token: &Parsed| ENGLISH_WORDS.contains(&token.core.as_str());
    for item in items[..start].iter().rev().take(ENGLISH_WINDOW) {
        let token = parse(&item.text);
        // This token closes the previous clause: it is not ours.
        if !token.trail.is_empty() || token.core.is_empty() {
            break;
        }
        if is_english(&token) {
            return true;
        }
    }
    if !number.trail.is_empty() {
        return false;
    }
    for item in items[number.end..].iter().take(ENGLISH_WINDOW) {
        let token = parse(&item.text);
        if is_english(&token) {
            return true;
        }
        if !token.trail.is_empty() || token.core.is_empty() {
            break;
        }
    }
    false
}

/// Whether the tokens after a number shared with English say all that
/// [`has_english_around`] reads: [`ENGLISH_WINDOW`] of them, or the end of the
/// clause.
fn clause_window_is_complete(after: &[Item]) -> bool {
    for (seen, item) in after.iter().take(ENGLISH_WINDOW).enumerate() {
        let token = parse(&item.text);
        if !token.trail.is_empty() || token.core.is_empty() {
            return true;
        }
        if seen + 1 == ENGLISH_WINDOW {
            return true;
        }
    }
    false
}

/// « neuf » as an adjective, not the number: after « tout » or « du »; after
/// « de » ending the clause (« quoi de neuf ? »); after a noun that an article
/// comes before (« un pull neuf »).
fn is_adjective_neuf(items: &[Item], start: usize, number: &Number) -> bool {
    let word = |k: Option<usize>| k.and_then(|k| items.get(k)).map(|item| parse(&item.text));
    let Some(previous) = word(start.checked_sub(1)) else {
        return false;
    };
    let core = previous.core.as_str();
    if matches!(core, "tout" | "toute" | "tous" | "toutes" | "du") {
        return true;
    }
    if core == "de" {
        return !number.trail.is_empty()
            || items
                .get(number.end)
                .is_none_or(|item| parse(&item.text).core.is_empty());
    }
    let before_noun = word(start.checked_sub(2));
    previous.trail.is_empty()
        && !core.is_empty()
        && !ARTICLES.contains(&core)
        && before_noun.is_some_and(|token| ARTICLES.contains(&token.core.as_str()))
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
            "it cost fifty cents.",
            "one cent",
            "I will take six.",
            "I will take six more.",
            "the cent",
        ] {
            assert_eq!(n(text), text);
        }
    }

    #[test]
    fn a_number_shared_with_english_is_in_digits_unless_english_is_around() {
        for (spoken, digits) in [
            ("il en reste six.", "il en reste 6."),
            ("j'en ai six.", "j'en ai 6."),
            ("nous sommes six.", "nous sommes 6."),
            ("ça fait neuf", "ça fait 9"),
            ("ils sont neuf", "ils sont 9"),
            ("six", "6"),
            ("sept", "7"),
            ("cent", "100"),
            ("il y a cent personnes", "il y a 100 personnes"),
            ("cent euros", "100 euros"),
            ("cent vingt", "120"),
            ("il en a six.", "il en a 6."),
            (
                "deux millions cinq cent mille personnes",
                "2500000 personnes",
            ),
            ("six millions de dollars", "6000000 de dollars"),
        ] {
            assert_eq!(n(spoken), digits, "{spoken}");
        }
        for english in [
            "six million dollars",
            "I paid six million.",
            "I paid six cents.",
            "one cent",
            "fifty cents",
            "I will take six.",
            "we paid six million dollars for it",
        ] {
            assert_eq!(n(english), english);
        }
    }

    #[test]
    fn the_adjective_neuf_stays_in_letters_the_number_does_not() {
        for text in [
            "quoi de neuf ?",
            "un pull neuf",
            "un pull neuf et un jean",
            "du neuf et du vieux",
            "il est tout neuf",
            "elle a acheté une voiture neuf.",
        ] {
            assert_eq!(n(text), text, "{text}");
        }
        assert_eq!(n("le neuf décembre"), "le 9 décembre");
        assert_eq!(n("neuf personnes"), "9 personnes");
        assert_eq!(n("à neuf heures"), "à 9 heures");
        assert_eq!(n("ça fait neuf"), "ça fait 9");
        assert_eq!(n("ils sont neuf"), "ils sont 9");
        assert_eq!(n("il y a neuf."), "il y a 9.");
        assert_eq!(n("de neuf ans"), "de 9 ans");
        assert_eq!(n("les neuf personnes"), "les 9 personnes");
    }

    #[test]
    fn scales_hours_and_digits_read_as_one_number() {
        assert_eq!(n("deux millions cinq cent mille"), "2500000");
        assert_eq!(n("un million"), "1000000");
        assert_eq!(n("trois milliards deux millions"), "3002000000");
        assert_eq!(n("mille et une nuits"), "1001 nuits");
        assert_eq!(n("une heure trente"), "1 h 30");
        assert_eq!(n("à une heure et demie"), "à 1 h 30");
        assert_eq!(n("une heure"), "une heure");
        assert_eq!(n("une heure de route"), "une heure de route");
        assert_eq!(n("14 heures trente"), "14 h 30");
        assert_eq!(n("14 heures"), "14 heures");
        assert_eq!(n("à 14h30."), "à 14 h 30.");
        assert_eq!(n("10 pour cent"), "10 %");
        assert_eq!(n("10% de plus"), "10 % de plus");
        assert_eq!(n("de 10%."), "de 10 %.");
        assert_eq!(n("14 h 30"), "14 h 30");
    }

    #[test]
    fn any_whitespace_separates_words_and_is_kept() {
        assert_eq!(n("trois\u{a0}tests"), "3\u{a0}tests");
        assert_eq!(
            n("trois\u{202f}tests\ndeux\u{a0}heures\u{202f}trente"),
            "3\u{202f}tests\n2 h 30"
        );
        assert_eq!(n("dix\npour cent"), "10 %");
        let text = "à\u{a0}quatre-vingt";
        assert_eq!(&text[..stable_prefix_len(text)], "à");
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
            "it cost fifty cents. the cent vingt and I will take six.",
            "à une heure trente, une heure et demie, une heure",
            "il est quatorze heures trente puis 14 heures trente puis 14h30 et 10 pour cent",
            "mille et une nuits et deux millions cinq cent mille personnes",
            "quoi de neuf ? un pull neuf, tout neuf, le neuf décembre, neuf personnes, il y a neuf.",
            "j'ai quatorze heures",
            "I paid six million. we paid six cents, one cent and 10% of it",
            "il en reste six. ça fait neuf, un pull neuf et un jean, du neuf et du vieux",
            "il y a cent personnes et six millions de dollars, I paid six million dollars",
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
        assert_eq!(held("à la fois un"), "à la fois");
        assert_eq!(held("il est une heure"), "il est");
        assert_eq!(held("il est une heure et"), "il est");
        assert_eq!(held("il a 10 pour"), "il a");
        assert_eq!(held("à 14 heures"), "à");
        // A number a guard rejects now is held too: what follows may change it.
        assert_eq!(held("the cent"), "the");
        assert_eq!(held("I will take six"), "I will take");
        // A number shared with English waits for three words or the clause end.
        assert_eq!(held("il en reste six"), "il en reste");
        assert_eq!(held("il en reste six tests"), "il en reste");
        assert_eq!(
            held("il en reste six tests de plus"),
            "il en reste six tests de plus"
        );
        assert_eq!(held("il en reste six, et"), "il en reste six, et");
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

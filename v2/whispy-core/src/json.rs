//! A small JSON reader and writer; the workspace has no serde, and the files
//! it handles (the bench sidecars, V1's `config.json`) are small.
//!
//! Objects are an ordered list, not a map: V2 rewrites a file V1 also writes,
//! and must hand back every key in the order it found it.

#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    /// A number written as an integer (no fraction, no exponent).
    Int(i64),
    /// Any other number.
    Number(f64),
    Text(String),
    List(Vec<Json>),
    Object(Vec<(String, Json)>),
}

/// Compact JSON text that parses back to an equal value (`to_string()` gives it).
/// Object keys keep their order, so a file read, changed in one key and written
/// back keeps the layout its owner gave it.
impl std::fmt::Display for Json {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut out = String::new();
        self.write(&mut out);
        f.write_str(&out)
    }
}

impl Json {
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(fields) => fields.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn text(&self) -> Option<&str> {
        match self {
            Json::Text(text) => Some(text),
            _ => None,
        }
    }

    /// Any number, integer or not, as `f64`.
    pub fn number(&self) -> Option<f64> {
        match self {
            Json::Number(number) => Some(*number),
            Json::Int(integer) => Some(*integer as f64),
            _ => None,
        }
    }

    /// The value when it was written as an integer.
    pub fn int(&self) -> Option<i64> {
        match self {
            Json::Int(integer) => Some(*integer),
            _ => None,
        }
    }

    pub fn bool(&self) -> Option<bool> {
        match self {
            Json::Bool(value) => Some(*value),
            _ => None,
        }
    }

    /// The layout Python's `json.dump(indent=2)` gives (V1 writes its config
    /// that way), so a file saved by V2 stays a readable, diff-friendly file.
    pub fn to_pretty_string(&self) -> String {
        let mut out = String::new();
        self.write_pretty(&mut out, 0);
        out
    }

    fn write_pretty(&self, out: &mut String, depth: usize) {
        let pad = |out: &mut String, depth: usize| out.push_str(&"  ".repeat(depth));
        match self {
            Json::List(items) if !items.is_empty() => {
                out.push_str("[\n");
                for (index, item) in items.iter().enumerate() {
                    if index > 0 {
                        out.push_str(",\n");
                    }
                    pad(out, depth + 1);
                    item.write_pretty(out, depth + 1);
                }
                out.push('\n');
                pad(out, depth);
                out.push(']');
            }
            Json::Object(fields) if !fields.is_empty() => {
                out.push_str("{\n");
                for (index, (key, value)) in fields.iter().enumerate() {
                    if index > 0 {
                        out.push_str(",\n");
                    }
                    pad(out, depth + 1);
                    write_string(key, out);
                    out.push_str(": ");
                    value.write_pretty(out, depth + 1);
                }
                out.push('\n');
                pad(out, depth);
                out.push('}');
            }
            other => other.write(out),
        }
    }

    fn write(&self, out: &mut String) {
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(value) => out.push_str(if *value { "true" } else { "false" }),
            Json::Int(integer) => out.push_str(&integer.to_string()),
            Json::Number(number) if number.is_finite() => {
                let shown = number.to_string();
                out.push_str(&shown);
                // `1.0` displays as `1`: keep it a float on the way back.
                if !shown.contains(['.', 'e', 'E']) {
                    out.push_str(".0");
                }
            }
            // JSON has no NaN or infinity.
            Json::Number(_) => out.push_str("null"),
            Json::Text(text) => write_string(text, out),
            Json::List(items) => {
                out.push('[');
                for (index, item) in items.iter().enumerate() {
                    if index > 0 {
                        out.push(',');
                    }
                    item.write(out);
                }
                out.push(']');
            }
            Json::Object(fields) => {
                out.push('{');
                for (index, (key, value)) in fields.iter().enumerate() {
                    if index > 0 {
                        out.push(',');
                    }
                    write_string(key, out);
                    out.push(':');
                    value.write(out);
                }
                out.push('}');
            }
        }
    }
}

/// Quotes, backslash and control characters escaped; everything else, accents
/// and emoji included, stays UTF-8 as it is.
fn write_string(text: &str, out: &mut String) {
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

pub fn parse_json(input: &str) -> Result<Json, String> {
    let mut parser = Parser {
        chars: input.chars().collect(),
        at: 0,
    };
    let value = parser.value()?;
    parser.skip_space();
    if parser.at != parser.chars.len() {
        return Err(format!("trailing data at {}", parser.at));
    }
    Ok(value)
}

struct Parser {
    chars: Vec<char>,
    at: usize,
}

impl Parser {
    fn skip_space(&mut self) {
        while self.chars.get(self.at).is_some_and(|c| c.is_whitespace()) {
            self.at += 1;
        }
    }

    fn eat(&mut self, expected: char) -> Result<(), String> {
        self.skip_space();
        if self.chars.get(self.at) == Some(&expected) {
            self.at += 1;
            Ok(())
        } else {
            Err(format!("expected {expected:?} at {}", self.at))
        }
    }

    fn word(&mut self, word: &str, value: Json) -> Result<Json, String> {
        let end = self.at + word.chars().count();
        let found: Option<String> = self.chars.get(self.at..end).map(|c| c.iter().collect());
        if found.as_deref() == Some(word) {
            self.at = end;
            Ok(value)
        } else {
            Err(format!("bad token at {}", self.at))
        }
    }

    fn value(&mut self) -> Result<Json, String> {
        self.skip_space();
        match self.chars.get(self.at).copied() {
            Some('{') => self.object(),
            Some('[') => self.list(),
            Some('"') => self.string().map(Json::Text),
            Some('t') => self.word("true", Json::Bool(true)),
            Some('f') => self.word("false", Json::Bool(false)),
            Some('n') => self.word("null", Json::Null),
            Some(_) => self.number(),
            None => Err("unexpected end".to_string()),
        }
    }

    fn object(&mut self) -> Result<Json, String> {
        self.eat('{')?;
        let mut fields = Vec::new();
        self.skip_space();
        if self.chars.get(self.at) == Some(&'}') {
            self.at += 1;
            return Ok(Json::Object(fields));
        }
        loop {
            self.skip_space();
            let key = self.string()?;
            self.eat(':')?;
            fields.push((key, self.value()?));
            self.skip_space();
            match self.chars.get(self.at) {
                Some(',') => self.at += 1,
                Some('}') => {
                    self.at += 1;
                    return Ok(Json::Object(fields));
                }
                _ => return Err(format!("expected , or }} at {}", self.at)),
            }
        }
    }

    fn list(&mut self) -> Result<Json, String> {
        self.eat('[')?;
        let mut items = Vec::new();
        self.skip_space();
        if self.chars.get(self.at) == Some(&']') {
            self.at += 1;
            return Ok(Json::List(items));
        }
        loop {
            items.push(self.value()?);
            self.skip_space();
            match self.chars.get(self.at) {
                Some(',') => self.at += 1,
                Some(']') => {
                    self.at += 1;
                    return Ok(Json::List(items));
                }
                _ => return Err(format!("expected , or ] at {}", self.at)),
            }
        }
    }

    fn number(&mut self) -> Result<Json, String> {
        let start = self.at;
        while self
            .chars
            .get(self.at)
            .is_some_and(|c| c.is_ascii_digit() || "+-.eE".contains(*c))
        {
            self.at += 1;
        }
        let text: String = self.chars[start..self.at].iter().collect();
        // A number written without fraction or exponent stays an integer, so a
        // keycode or a version written back is not turned into `61.0`.
        if let Ok(integer) = text.parse::<i64>() {
            return Ok(Json::Int(integer));
        }
        text.parse()
            .map(Json::Number)
            .map_err(|_| format!("bad number {text:?} at {start}"))
    }

    fn hex4(&mut self) -> Result<u32, String> {
        let digits: String = self
            .chars
            .get(self.at..self.at + 4)
            .ok_or("short \\u escape")?
            .iter()
            .collect();
        self.at += 4;
        u32::from_str_radix(&digits, 16).map_err(|_| format!("bad \\u escape {digits:?}"))
    }

    fn string(&mut self) -> Result<String, String> {
        if self.chars.get(self.at) != Some(&'"') {
            return Err(format!("expected a string at {}", self.at));
        }
        self.at += 1;
        let mut out = String::new();
        loop {
            let c = *self.chars.get(self.at).ok_or("unterminated string")?;
            self.at += 1;
            match c {
                '"' => return Ok(out),
                '\\' => {
                    let escape = *self.chars.get(self.at).ok_or("unterminated escape")?;
                    self.at += 1;
                    match escape {
                        'n' => out.push('\n'),
                        't' => out.push('\t'),
                        'r' => out.push('\r'),
                        'b' => out.push('\u{8}'),
                        'f' => out.push('\u{c}'),
                        'u' => {
                            let mut code = self.hex4()?;
                            if (0xD800..0xDC00).contains(&code)
                                && self.chars.get(self.at..self.at + 2) == Some(&['\\', 'u'])
                            {
                                self.at += 2;
                                let low = self.hex4()?;
                                code = 0x10000
                                    + ((code - 0xD800) << 10)
                                    + (low.wrapping_sub(0xDC00) & 0x3FF);
                            }
                            out.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                        }
                        other => out.push(other),
                    }
                }
                c => out.push(c),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_reads_strings_escapes_and_nesting() {
        let value = parse_json(
            r#"{"ref": "léger \"oui\"\n😀", "kind": "chunk", "origin": {"a": [1, 2.5, null, true]}, "reviewed": false}"#,
        )
        .unwrap();
        assert_eq!(
            value.get("ref").and_then(Json::text),
            Some("léger \"oui\"\n😀")
        );
        assert_eq!(value.get("reviewed"), Some(&Json::Bool(false)));
        assert!(parse_json("{\"a\": 1} x").is_err());
        assert!(parse_json("{\"a\": ").is_err());
    }

    #[test]
    fn integers_stay_integers_and_floats_floats() {
        let value = parse_json(r#"{"a": 61, "b": 0.3, "c": 2.0, "d": -4, "e": 1e-05}"#).unwrap();
        assert_eq!(value.get("a"), Some(&Json::Int(61)));
        assert_eq!(value.get("b"), Some(&Json::Number(0.3)));
        assert_eq!(value.get("c"), Some(&Json::Number(2.0)));
        assert_eq!(value.get("d"), Some(&Json::Int(-4)));
        assert_eq!(value.get("e").and_then(Json::number), Some(1e-5));
        assert_eq!(value.get("a").and_then(Json::number), Some(61.0));
    }

    #[test]
    fn a_v1_config_round_trips_with_its_key_order() {
        let text = r#"{"_version":3,"copy_to_clipboard":true,"trigger_mode":"toggle","trigger":61,"max_chunk_s":0.3,"silence_s":2.0,"vocabulary":["Zénika","naïve","日本語"],"nested":{"inner":{"k":null,"ok":false}},"start_at_login":true}"#;
        let value = parse_json(text).unwrap();
        assert_eq!(value.to_string(), text);
        assert_eq!(parse_json(&value.to_string()).unwrap(), value);
    }

    #[test]
    fn a_whitespace_laden_file_parses_and_writes_compact() {
        let value = parse_json("{\n  \"a\": [1,\n 2],\n  \"b\": {}\n}\n").unwrap();
        assert_eq!(value.to_string(), r#"{"a":[1,2],"b":{}}"#);
    }

    #[test]
    fn strings_are_escaped_per_json() {
        let text = Json::Text("say \"hi\" \\ \n\t\r \u{1}\u{1f} é😀".to_string());
        let written = text.to_string();
        assert_eq!(
            written,
            "\"say \\\"hi\\\" \\\\ \\n\\t\\r \\u0001\\u001f é😀\""
        );
        assert_eq!(parse_json(&written).unwrap(), text);
    }

    #[test]
    fn keys_are_escaped_too() {
        let object = Json::Object(vec![("a\"b".to_string(), Json::Null)]);
        assert_eq!(object.to_string(), r#"{"a\"b":null}"#);
        assert_eq!(parse_json(&object.to_string()).unwrap(), object);
    }

    #[test]
    fn pretty_output_matches_python_indent_two_and_round_trips() {
        let text = "{\n  \"a\": 1,\n  \"b\": [\n    \"é\",\n    2.5\n  ],\n  \"c\": {},\n  \"d\": [],\n  \"e\": {\n    \"f\": null\n  }\n}";
        let value = parse_json(text).unwrap();
        assert_eq!(value.to_pretty_string(), text);
    }

    #[test]
    fn non_finite_numbers_are_written_as_null() {
        assert_eq!(Json::Number(f64::NAN).to_string(), "null");
        assert_eq!(Json::Number(1.0).to_string(), "1.0");
    }
}

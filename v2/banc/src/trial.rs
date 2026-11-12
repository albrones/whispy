//! The trial report: `banc --trial [--since YYYY-MM-DD] [--journal PATH] [--v1-log-dir DIR]`.
//!
//! Reads the journal the V2 app appends to (`~/.whispy/v2/dictations.jsonl`,
//! one flat JSON object per dictation, never the text) and prints the numbers
//! the exit criteria of `v2/TRIAL.md` are read from: dictation and day counts,
//! outcomes, release-to-delivery latency, the lost clips kept, and V1's
//! lost-speech share beside V2's.
//!
//! Journal keys: `time` (unix seconds as a number, or an RFC3339 string),
//! `duration_s`, `latency_s`, `trigger`, `outcome`, `engine`, `length`.
//! A line that does not parse is skipped and counted, never fatal.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use crate::measure::percentile;
use whispy_core::json::{parse_json, Json};

/// The outcomes the app writes, in report order.
const OUTCOMES: [&str; 6] = [
    "inserted",
    "clipboard",
    "empty",
    "heard_nothing",
    "lost",
    "failed",
];

const SECONDS_PER_DAY: i64 = 86_400;

#[derive(Debug, Clone, PartialEq)]
pub struct Entry {
    /// Unix seconds.
    pub time: i64,
    pub duration_s: f64,
    pub latency_s: f64,
    pub outcome: String,
}

/// Parses one journal line; the text of a dictation is never in it.
pub fn parse_entry(line: &str) -> Result<Entry, String> {
    let json = parse_json(line)?;
    let number = |key: &str| {
        json.get(key)
            .and_then(Json::number)
            .ok_or_else(|| format!("missing number {key:?}"))
    };
    let time = match json.get("time") {
        Some(Json::Int(seconds)) => *seconds,
        Some(Json::Number(seconds)) => *seconds as i64,
        Some(Json::Text(text)) => parse_rfc3339(text)?,
        _ => return Err("missing time".to_string()),
    };
    let outcome = json
        .get("outcome")
        .and_then(Json::text)
        .ok_or("missing outcome")?
        .to_string();
    Ok(Entry {
        time,
        duration_s: number("duration_s")?,
        latency_s: number("latency_s")?,
        outcome,
    })
}

/// Days since 1970-01-01 of a civil date (proleptic Gregorian).
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = if month <= 2 { year - 1 } else { year };
    let era = year.div_euclid(400);
    let year_of_era = year - era * 400;
    let day_of_year = (153 * (month + if month > 2 { -3 } else { 9 }) + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

/// The civil date of a day count; the inverse of `days_from_civil`.
fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let day_of_era = z - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let mp = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = year_of_era + era * 400 + i64::from(month <= 2);
    (year, month, day)
}

/// `YYYY-MM-DD` to the unix second of that day's UTC midnight.
pub fn parse_date(text: &str) -> Result<i64, String> {
    let bad = || format!("{text:?} is not a YYYY-MM-DD date");
    let mut parts = text.split('-');
    let (Some(y), Some(m), Some(d), None) =
        (parts.next(), parts.next(), parts.next(), parts.next())
    else {
        return Err(bad());
    };
    let year: i64 = y.parse().map_err(|_| bad())?;
    let month: i64 = m.parse().map_err(|_| bad())?;
    let day: i64 = d.parse().map_err(|_| bad())?;
    if y.len() != 4 || !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return Err(bad());
    }
    Ok(days_from_civil(year, month, day) * SECONDS_PER_DAY)
}

/// `YYYY-MM-DDTHH:MM:SS[.fff](Z|±HH:MM)` to unix seconds.
fn parse_rfc3339(text: &str) -> Result<i64, String> {
    let bad = || format!("{text:?} is not an RFC3339 time");
    let (date, rest) = text.split_once(['T', 't', ' ']).ok_or_else(bad)?;
    let midnight = parse_date(date)?;
    let split = rest.find(['Z', 'z', '+', '-']).unwrap_or(rest.len());
    let (clock, zone) = rest.split_at(split);
    let mut fields = clock.split(':');
    let mut next = || -> Result<f64, String> {
        fields
            .next()
            .ok_or_else(bad)?
            .parse::<f64>()
            .map_err(|_| bad())
    };
    let (hours, minutes, seconds) = (next()?, next()?, next()?);
    let offset = match zone.chars().next() {
        None | Some('Z') | Some('z') => 0,
        Some(sign) => {
            let (h, m) = zone[1..].split_once(':').ok_or_else(bad)?;
            let magnitude = h.parse::<i64>().map_err(|_| bad())? * 3600
                + m.parse::<i64>().map_err(|_| bad())? * 60;
            if sign == '-' {
                -magnitude
            } else {
                magnitude
            }
        }
    };
    Ok(midnight + (hours * 3600.0 + minutes * 60.0 + seconds) as i64 - offset)
}

fn format_date(unix_seconds: i64) -> String {
    let (year, month, day) = civil_from_days(unix_seconds.div_euclid(SECONDS_PER_DAY));
    format!("{year:04}-{month:02}-{day:02}")
}

/// Journal entries from `since` on (unix seconds, inclusive) and the number of
/// lines that could not be read. Blank lines are neither.
pub fn parse_journal(text: &str, since: Option<i64>) -> (Vec<Entry>, usize) {
    let mut entries = Vec::new();
    let mut malformed = 0;
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        match parse_entry(line) {
            Ok(entry) if since.is_none_or(|since| entry.time >= since) => entries.push(entry),
            Ok(_) => {}
            Err(_) => malformed += 1,
        }
    }
    (entries, malformed)
}

/// Lost-speech share, weighted by audio duration because V1 logs per streamed
/// chunk and V2 per dictation, so counts would not compare.
fn lost_share(lost_seconds: f64, spoken_seconds: f64) -> Option<f64> {
    let total = lost_seconds + spoken_seconds;
    (total > 0.0).then(|| 100.0 * lost_seconds / total)
}

/// V2's share, computed like V1's: lost seconds over the seconds of speech
/// that was either delivered (`inserted`, `clipboard`) or lost. `empty` and
/// `heard_nothing` are left out: V1's "Transcribed" lines are speech that
/// produced text, and its "Lost speech" lines are speech that did not.
pub fn v2_lost_share(entries: &[Entry]) -> Option<f64> {
    let sum = |wanted: &[&str]| -> f64 {
        entries
            .iter()
            .filter(|entry| wanted.contains(&entry.outcome.as_str()))
            .map(|entry| entry.duration_s)
            // An empty float sum is -0.0, printed « -0.0 % ».
            .fold(0.0, |total, seconds| total + seconds)
    };
    lost_share(sum(&["lost"]), sum(&["inserted", "clipboard"]))
}

/// (transcribed seconds, lost seconds) from the lines of V1 logs, e.g.
/// `[INFO] [audio] Transcribed a 8.28s clip (91 characters).` and
/// `[WARNING] [audio] Lost speech: ... for a 2.79s clip that cleared ...`.
pub fn v1_seconds(log: &str) -> (f64, f64) {
    let (mut transcribed, mut lost) = (0.0, 0.0);
    for line in log.lines() {
        if let Some(seconds) = clip_seconds(line, "Transcribed a ") {
            transcribed += seconds;
        } else if line.contains("Lost speech:") {
            if let Some(seconds) = clip_seconds(line, " for a ") {
                lost += seconds;
            }
        }
    }
    (transcribed, lost)
}

/// The number between `marker` and `s clip` in `line`.
fn clip_seconds(line: &str, marker: &str) -> Option<f64> {
    let rest = &line[line.find(marker)? + marker.len()..];
    rest[..rest.find("s clip")?].parse().ok()
}

/// V1's logs: the live file and its one rotation, whole (the lines carry no
/// date). `.whispy.log.presparakeet` is a pre-Parakeet snapshot and is never read.
fn read_v1_logs(dir: &Path) -> (f64, f64) {
    [".whispy.log", ".whispy.log.1"]
        .iter()
        .filter_map(|name| std::fs::read(dir.join(name)).ok())
        .map(|bytes| v1_seconds(&String::from_utf8_lossy(&bytes)))
        .fold((0.0, 0.0), |(t, l), (more_t, more_l)| {
            (t + more_t, l + more_l)
        })
}

/// Lost clips (`lost-<unix-ms>.wav`) whose time is at or after `since`, oldest first.
fn lost_clips(dir: &Path, since: Option<i64>) -> Vec<PathBuf> {
    let Ok(read) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut clips: Vec<(i64, PathBuf)> = read
        .filter_map(Result::ok)
        .filter_map(|file| {
            let name = file.file_name().into_string().ok()?;
            let millis: i64 = name
                .strip_prefix("lost-")?
                .strip_suffix(".wav")?
                .parse()
                .ok()?;
            let seconds = millis / 1000;
            since
                .is_none_or(|since| seconds >= since)
                .then(|| (seconds, file.path()))
        })
        .collect();
    clips.sort();
    clips.into_iter().map(|(_, path)| path).collect()
}

struct Options {
    since: Option<i64>,
    journal: PathBuf,
    v1_log_dir: PathBuf,
    lost_dir: PathBuf,
}

fn home() -> PathBuf {
    PathBuf::from(std::env::var_os("HOME").unwrap_or_default())
}

fn parse_options(args: &[String]) -> Result<Options, String> {
    let mut options = Options {
        since: None,
        journal: home().join(".whispy/v2/dictations.jsonl"),
        v1_log_dir: home(),
        lost_dir: home().join(".whispy/v2-lost"),
    };
    let mut args = args.iter();
    while let Some(flag) = args.next() {
        let mut value = || args.next().ok_or_else(|| format!("{flag} takes a value"));
        match flag.as_str() {
            "--since" => options.since = Some(parse_date(value()?)?),
            "--journal" => options.journal = PathBuf::from(value()?),
            "--v1-log-dir" => options.v1_log_dir = PathBuf::from(value()?),
            other => return Err(format!("unknown option {other:?} for --trial")),
        }
    }
    Ok(options)
}

pub fn run(args: &[String]) -> Result<ExitCode, String> {
    let options = parse_options(args)?;
    print!("{}", report(&options));
    Ok(ExitCode::SUCCESS)
}

fn report(options: &Options) -> String {
    let mut out = String::new();
    let period = match options.since {
        Some(since) => format!("since {}", format_date(since)),
        None => "whole journal".to_string(),
    };
    out += &format!("Trial report ({period})\n\n");

    let (entries, malformed) = match std::fs::read_to_string(&options.journal) {
        Ok(text) => parse_journal(&text, options.since),
        Err(_) => {
            out += &format!(
                "No dictation was recorded ({} not found).\n",
                options.journal.display()
            );
            return out + &v1_section(options, &[]);
        }
    };
    if entries.is_empty() {
        out += "No dictation was recorded in this period.\n";
    } else {
        let mut days: Vec<i64> = entries
            .iter()
            .map(|entry| entry.time.div_euclid(SECONDS_PER_DAY))
            .collect();
        days.sort_unstable();
        days.dedup();
        out += &format!("{:<22}{}\n", "Dictations", entries.len());
        out += &format!("{:<22}{} (UTC)\n\n", "Days with dictation", days.len());
        out += "Outcomes\n";
        for name in OUTCOMES {
            let count = entries.iter().filter(|entry| entry.outcome == name).count();
            out += &format!(
                "  {name:<20}{count:>5}  {:>5.1} %\n",
                100.0 * count as f64 / entries.len() as f64
            );
        }
        let latencies: Vec<f64> = entries
            .iter()
            .filter(|entry| entry.outcome == "inserted")
            .map(|entry| entry.latency_s)
            .collect();
        out += "\nRelease-to-delivery latency (inserted dictations)\n";
        if latencies.is_empty() {
            out += "  no inserted dictation\n";
        } else {
            let max = latencies.iter().copied().fold(0.0, f64::max);
            out += &format!(
                "  p50 {:.2} s   p95 {:.2} s   max {:.2} s   (n={})\n",
                percentile(&latencies, 50.0),
                percentile(&latencies, 95.0),
                max,
                latencies.len()
            );
        }
    }
    if malformed > 0 {
        out += &format!("\n{malformed} unreadable journal line(s) skipped.\n");
    }

    let clips = lost_clips(&options.lost_dir, options.since);
    out += &format!(
        "\nLost clips kept in {} ({})\n",
        options.lost_dir.display(),
        clips.len()
    );
    for clip in &clips {
        out += &format!("  {}\n", clip.display());
    }
    out + &v1_section(options, &entries)
}

fn v1_section(options: &Options, entries: &[Entry]) -> String {
    let (transcribed, lost) = read_v1_logs(&options.v1_log_dir);
    let mut out = "\nLost-speech share, weighted by audio seconds\n".to_string();
    match lost_share(lost, transcribed) {
        Some(share) => {
            out += &format!(
                "  {:<6}{share:>5.1} %   ({lost:.0} s lost of {:.0} s)\n",
                "V1",
                lost + transcribed
            );
        }
        None => {
            out +=
                "  V1    comparison unavailable: no Transcribed or Lost speech line in V1's logs\n"
        }
    }
    match v2_lost_share(entries) {
        Some(share) => out += &format!("  {:<6}{share:>5.1} %\n", "V2"),
        None => out += "  V2    not computable: no inserted, clipboard or lost dictation\n",
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line(time: i64, duration: f64, latency: f64, outcome: &str) -> String {
        format!(
            "{{\"time\":{time},\"duration_s\":{duration},\"latency_s\":{latency},\"trigger\":\"fn\",\"outcome\":\"{outcome}\",\"engine\":\"parakeet\",\"length\":42}}"
        )
    }

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("banc-trial-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn options(dir: &Path) -> Options {
        Options {
            since: None,
            journal: dir.join("dictations.jsonl"),
            v1_log_dir: dir.join("v1"),
            lost_dir: dir.join("lost"),
        }
    }

    #[test]
    fn latency_percentiles_of_twenty_inserted_dictations() {
        let journal: String = (1..=20)
            .map(|i| line(1_700_000_000, 4.0, f64::from(i) / 10.0, "inserted") + "\n")
            .collect();
        let dir = scratch("latency");
        std::fs::write(dir.join("dictations.jsonl"), journal).unwrap();
        let text = report(&options(&dir));
        assert!(text.contains("p95 1.90 s"), "{text}");
        assert!(text.contains("max 2.00 s"), "{text}");
        assert!(text.contains("p50 1.00 s"), "{text}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_missing_journal_says_so_and_succeeds() {
        let dir = scratch("missing");
        let text = report(&options(&dir));
        assert!(text.contains("No dictation was recorded"), "{text}");
        let args = vec![
            "--journal".to_string(),
            dir.join("absent.jsonl").display().to_string(),
            "--v1-log-dir".to_string(),
            dir.display().to_string(),
        ];
        assert_eq!(run(&args).unwrap(), ExitCode::SUCCESS);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn since_filters_by_utc_day_and_malformed_lines_are_counted() {
        let day2 = parse_date("2026-11-02").unwrap();
        let journal = format!(
            "{}\n{}\nnot json\n\n{}\n",
            line(day2 - 1, 1.0, 1.0, "inserted"),
            line(day2, 1.0, 1.0, "inserted"),
            line(day2 + 90_000, 1.0, 1.0, "lost"),
        );
        let (entries, malformed) = parse_journal(&journal, Some(day2));
        assert_eq!(entries.len(), 2);
        assert_eq!(malformed, 1);
        assert_eq!(parse_journal(&journal, None).0.len(), 3);
    }

    #[test]
    fn dates_round_trip_and_rfc3339_matches_unix_seconds() {
        assert_eq!(parse_date("1970-01-02").unwrap(), 86_400);
        assert_eq!(format_date(parse_date("2026-11-04").unwrap()), "2026-11-04");
        assert_eq!(
            parse_rfc3339("2026-11-04T10:00:00+01:00").unwrap(),
            parse_date("2026-11-04").unwrap() + 9 * 3600
        );
        assert!(parse_date("04/11/2026").is_err());
        let entry = parse_entry(
            "{\"time\":\"2026-11-04T00:00:01Z\",\"duration_s\":1,\"latency_s\":1,\"outcome\":\"lost\",\"engine\":null}",
        )
        .unwrap();
        assert_eq!(entry.time, parse_date("2026-11-04").unwrap() + 1);
    }

    #[test]
    fn lost_share_is_weighted_by_duration_beside_v1() {
        let dir = scratch("share");
        std::fs::create_dir_all(dir.join("v1")).unwrap();
        let v1 = "[INFO] [audio] Transcribed a 60.00s clip (500 characters).\n\
                  [INFO] [audio] Transcribed a 35.00s clip (300 characters).\n\
                  [WARNING] [audio] Lost speech: the model returned no text for a 5.00s clip that cleared every gate (peak RMS 0.007022, voiced 0.60s, kept as lost-1.wav).\n\
                  [INFO] [other] unrelated line\n";
        std::fs::write(dir.join("v1/.whispy.log"), v1).unwrap();
        // The pre-Parakeet snapshot must not count.
        std::fs::write(
            dir.join("v1/.whispy.log.presparakeet"),
            "[INFO] [audio] Transcribed a 999.00s clip (1 characters).\n",
        )
        .unwrap();
        let journal = line(1, 196.0, 1.0, "inserted")
            + "\n"
            + &line(2, 4.0, 1.0, "lost")
            + "\n"
            + &line(3, 50.0, 1.0, "heard_nothing")
            + "\n";
        std::fs::write(dir.join("dictations.jsonl"), journal).unwrap();
        let text = report(&options(&dir));
        assert!(text.contains("V1      5.0 %"), "{text}");
        assert!(text.contains("V2      2.0 %"), "{text}");
        let nothing_lost = [parse_entry(&line(4, 3.0, 1.0, "inserted")).unwrap()];
        assert_eq!(
            v2_lost_share(&nothing_lost).map(|share| share.to_string()),
            Some("0".to_string())
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn no_v1_line_makes_the_comparison_unavailable() {
        let dir = scratch("nov1");
        let text = report(&options(&dir));
        assert!(text.contains("comparison unavailable"), "{text}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn lost_clips_are_listed_by_their_timestamp() {
        let dir = scratch("clips");
        let day = parse_date("2026-11-02").unwrap();
        for millis in [(day - 10) * 1000, (day + 10) * 1000] {
            std::fs::write(dir.join(format!("lost-{millis}.wav")), b"").unwrap();
        }
        std::fs::write(dir.join("notes.txt"), b"").unwrap();
        assert_eq!(lost_clips(&dir, None).len(), 2);
        assert_eq!(lost_clips(&dir, Some(day)).len(), 1);
        let _ = std::fs::remove_dir_all(&dir);
    }
}

//! NVIDIA Parakeet TDT 0.6b v3, int8 ONNX, on the ONNX Runtime CPU provider.
//!
//! A port of onnx-asr's `NemoConformerTdt` greedy decoding, the code path
//! V1 runs, so both versions read the same weights the same way. CPU only on
//! purpose: under CoreML a 180 s clip reached 25 GB and took the Mac down (V1,
//! 2026-09-29).

use std::path::Path;

use ort::session::builder::GraphOptimizationLevel;
use ort::session::Session;
use ort::value::Tensor;

use crate::mel::{MelExtractor, MEL_BINS};
use crate::{Error, Transcriber, Word};

const MAX_TOKENS_PER_STEP: usize = 10;
const WORD_START: char = '\u{2581}';
/// Digital silence put before and after every input. V1 measured it
/// (fcf7861): cut tight to its speech, a clip reaches Parakeet with no
/// silence around it, and Parakeet drops phrases or answers French in
/// English; 0.25 s cured that without losing a mixed-language clip. whisper
/// needs none: it pads every input to 30 s itself.
pub const FRAME_S: f32 = 0.25;
/// One encoder frame: 8 mel hops of 10 ms (the encoder subsamples by 8).
const ENCODER_FRAME_S: f32 = 0.08;

/// A token the decoder emitted, with the encoder frame it was emitted at and
/// the duration (in frames) the TDT head predicted for it.
struct Emitted {
    token: usize,
    frame: usize,
    duration: usize,
}

pub struct Parakeet {
    encoder: Session,
    decoder_joint: Session,
    mel: MelExtractor,
    vocabulary: Vec<String>,
    blank: usize,
    state_shapes: [Vec<i64>; 2],
}

impl Parakeet {
    /// Loads `encoder-model.int8.onnx`, `decoder_joint-model.int8.onnx` and `vocab.txt` from `dir`.
    pub fn load(dir: &Path) -> Result<Self, Error> {
        let encoder = session(&dir.join("encoder-model.int8.onnx"))?;
        let decoder_joint = session(&dir.join("decoder_joint-model.int8.onnx"))?;
        let (vocabulary, blank) = read_vocabulary(&dir.join("vocab.txt"))?;
        let state_shapes = [
            state_shape(&decoder_joint, "input_states_1")?,
            state_shape(&decoder_joint, "input_states_2")?,
        ];
        Ok(Parakeet {
            encoder,
            decoder_joint,
            mel: MelExtractor::new(),
            vocabulary,
            blank,
            state_shapes,
        })
    }

    /// Encoder output as one `Vec` per frame, valid frames only.
    fn encode(&mut self, samples: &[f32]) -> Result<Vec<Vec<f32>>, Error> {
        let Some(features) = self.mel.features(samples) else {
            return Ok(Vec::new());
        };
        let signal = Tensor::from_array(([1usize, MEL_BINS, features.frames], features.data))?;
        let length = Tensor::from_array(([1usize], vec![features.valid_frames as i64]))?;
        let outputs = self
            .encoder
            .run(ort::inputs!["audio_signal" => signal, "length" => length])?;
        let (shape, encoded) = outputs["outputs"].try_extract_tensor::<f32>()?;
        let (_, lengths) = outputs["encoded_lengths"].try_extract_tensor::<i64>()?;
        let (dimension, frames) = (shape[1] as usize, shape[2] as usize);
        let valid = (lengths[0].max(0) as usize).min(frames);
        // [1, dimension, frames] -> one row per frame.
        Ok((0..valid)
            .map(|frame| {
                (0..dimension)
                    .map(|d| encoded[d * frames + frame])
                    .collect()
            })
            .collect())
    }

    fn zero_states(&self) -> [Vec<f32>; 2] {
        self.state_shapes
            .clone()
            .map(|shape| vec![0.0; shape.iter().product::<i64>() as usize])
    }

    /// One decoder+joint step: (token logits, duration index, next states).
    fn step(
        &mut self,
        previous: usize,
        frame: &[f32],
        states: &[Vec<f32>; 2],
    ) -> Result<(usize, usize, [Vec<f32>; 2]), Error> {
        let inputs = ort::inputs![
            "encoder_outputs" => Tensor::from_array(([1usize, frame.len(), 1], frame.to_vec()))?,
            "targets" => Tensor::from_array(([1usize, 1], vec![previous as i32]))?,
            "target_length" => Tensor::from_array(([1usize], vec![1i32]))?,
            "input_states_1" => Tensor::from_array((self.state_shapes[0].clone(), states[0].clone()))?,
            "input_states_2" => Tensor::from_array((self.state_shapes[1].clone(), states[1].clone()))?,
        ];
        let outputs = self.decoder_joint.run(inputs)?;
        let (_, logits) = outputs["outputs"].try_extract_tensor::<f32>()?;
        let vocabulary_size = self.vocabulary.len();
        if logits.len() < vocabulary_size {
            return Err(Error::Inference(format!(
                "decoder returned {} logits, expected at least the {vocabulary_size} vocabulary entries",
                logits.len()
            )));
        }
        let token = argmax(&logits[..vocabulary_size]);
        let duration = if logits.len() > vocabulary_size {
            argmax(&logits[vocabulary_size..])
        } else {
            0
        };
        let (_, state_1) = outputs["output_states_1"].try_extract_tensor::<f32>()?;
        let (_, state_2) = outputs["output_states_2"].try_extract_tensor::<f32>()?;
        Ok((token, duration, [state_1.to_vec(), state_2.to_vec()]))
    }

    fn decode(&mut self, frames: &[Vec<f32>]) -> Result<Vec<Emitted>, Error> {
        let mut states = self.zero_states();
        let mut tokens: Vec<Emitted> = Vec::new();
        let (mut t, mut emitted) = (0, 0);
        while t < frames.len() {
            let previous = tokens.last().map_or(self.blank, |last| last.token);
            let (token, duration, next_states) = self.step(previous, &frames[t], &states)?;
            if token != self.blank {
                states = next_states;
                tokens.push(Emitted {
                    token,
                    frame: t,
                    duration,
                });
                emitted += 1;
            }
            if duration > 0 {
                t += duration;
                emitted = 0;
            } else if token == self.blank || emitted == MAX_TOKENS_PER_STEP {
                t += 1;
                emitted = 0;
            }
        }
        Ok(tokens)
    }

    /// The one inference path: `samples` framed in silence, encoded, decoded.
    /// Returns the tokens and the number of encoder frames of the framed input.
    fn run(&mut self, samples: &[f32]) -> Result<(Vec<Emitted>, usize), Error> {
        let framed = crate::audio::padded(samples, FRAME_S, FRAME_S);
        let frames = self.encode(&framed)?;
        let count = frames.len();
        Ok((self.decode(&frames)?, count))
    }

    /// The tokens' pieces end to end, one entry per character with the index
    /// of the token that printed it, then detokenized.
    fn spelled(&self, tokens: &[Emitted]) -> Vec<(char, usize)> {
        let mut joined = Vec::new();
        for (index, emitted) in tokens.iter().enumerate() {
            joined.extend(
                self.vocabulary[emitted.token]
                    .chars()
                    .map(|character| (character, index)),
            );
        }
        detokenize_owned(&joined)
    }
}

impl Transcriber for Parakeet {
    fn name(&self) -> &'static str {
        "parakeet"
    }

    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
        let (tokens, _) = self.run(samples)?;
        Ok(self.spelled(&tokens).into_iter().map(|(c, _)| c).collect())
    }

    fn transcribe_timed(&mut self, samples: &[f32]) -> Result<Option<Vec<Word>>, Error> {
        let (tokens, _) = self.run(samples)?;
        let duration_s = samples.len() as f32 / crate::audio::SAMPLE_RATE as f32;
        Ok(Some(words_of(&self.spelled(&tokens), &tokens, duration_s)))
    }
}

/// Seconds in the caller's samples of an encoder frame boundary: the frame
/// clock starts `FRAME_S` before the samples, and a time is within the input.
fn frame_time(frame: usize, duration_s: f32) -> f32 {
    (frame as f32 * ENCODER_FRAME_S - FRAME_S).clamp(0.0, duration_s)
}

/// Splits the detokenized characters at their single spaces; a word starts at
/// its first token's frame and ends at its last token's frame plus that
/// token's duration (one frame at least).
fn words_of(spelled: &[(char, usize)], tokens: &[Emitted], duration_s: f32) -> Vec<Word> {
    spelled
        .split(|&(character, _)| character == ' ')
        .filter(|word| !word.is_empty())
        .map(|word| {
            let first = &tokens[word[0].1];
            let last = &tokens[word[word.len() - 1].1];
            Word {
                text: word.iter().map(|&(character, _)| character).collect(),
                start_s: frame_time(first.frame, duration_s),
                end_s: frame_time(last.frame + last.duration.max(1), duration_s),
            }
        })
        .collect()
}

/// Memory settings measured on a 180 s dictation (v2/bench/REPORT.md):
/// ONNX Runtime's defaults peaked at 1.67 GB; without memory patterns and
/// weight prepacking, initializers outside the arena, 1.09 GB, same text.
fn session(path: &Path) -> Result<Session, Error> {
    let loading = |error: String| Error::Inference(format!("loading {}: {error}", path.display()));
    Session::builder()?
        .with_optimization_level(GraphOptimizationLevel::Level3)
        .and_then(|builder| builder.with_memory_pattern(false))
        .and_then(|builder| builder.with_prepacking(false))
        .and_then(|builder| builder.with_device_allocator_for_initializers())
        .and_then(|builder| builder.commit_from_file(path))
        .map_err(|error| loading(error.to_string()))
}

fn state_shape(session: &Session, name: &str) -> Result<Vec<i64>, Error> {
    let input = session
        .inputs
        .iter()
        .find(|input| input.name == name)
        .ok_or_else(|| {
            Error::Inference(format!(
                "decoder has no input {name}; is this the Parakeet TDT decoder_joint model?"
            ))
        })?;
    let shape = input
        .input_type
        .tensor_shape()
        .ok_or_else(|| Error::Inference(format!("decoder input {name} is not a tensor")))?;
    // [layers, batch (dynamic), hidden]: a batch of one.
    Ok(shape
        .iter()
        .enumerate()
        .map(|(axis, &size)| if axis == 1 { 1 } else { size.max(1) })
        .collect())
}

/// `vocab.txt` lines are `<token> <id>`; the word-start mark becomes a space.
fn read_vocabulary(path: &Path) -> Result<(Vec<String>, usize), Error> {
    let text = std::fs::read_to_string(path)?;
    let mut entries: Vec<(usize, String)> = Vec::new();
    for line in text.lines().filter(|line| !line.is_empty()) {
        let (token, id) = line
            .rsplit_once(' ')
            .and_then(|(token, id)| id.parse::<usize>().ok().map(|id| (token, id)))
            .ok_or_else(|| {
                Error::Inference(format!(
                    "{}: malformed line {line:?}, expected \"<token> <id>\"",
                    path.display()
                ))
            })?;
        entries.push((id, token.replace(WORD_START, " ")));
    }
    entries.sort_by_key(|(id, _)| *id);
    let vocabulary: Vec<String> = entries.into_iter().map(|(_, token)| token).collect();
    let blank = vocabulary
        .iter()
        .position(|token| token == "<blk>")
        .ok_or_else(|| Error::Inference(format!("{} has no <blk> token", path.display())))?;
    Ok((vocabulary, blank))
}

fn argmax(values: &[f32]) -> usize {
    values
        .iter()
        .enumerate()
        .fold((0, f32::NEG_INFINITY), |best, (i, &v)| {
            if v > best.1 {
                (i, v)
            } else {
                best
            }
        })
        .0
}

fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

#[cfg(test)]
/// onnx-asr's `re.sub(r"\A\s|\s\B|(\s)\b", ...)`: drop leading whitespace and
/// whitespace not followed by a word character, keep the rest as one space.
fn detokenize(joined: &str) -> String {
    let owned: Vec<(char, usize)> = joined.chars().map(|c| (c, 0)).collect();
    detokenize_owned(&owned)
        .into_iter()
        .map(|(c, _)| c)
        .collect()
}

/// [`detokenize`] on characters that each remember what produced them.
fn detokenize_owned<T: Copy>(joined: &[(char, T)]) -> Vec<(char, T)> {
    let mut text = Vec::with_capacity(joined.len());
    for (i, &(c, owner)) in joined.iter().enumerate() {
        if !c.is_whitespace() {
            text.push((c, owner));
            continue;
        }
        let is_followed_by_word = joined
            .get(i + 1)
            .is_some_and(|&(next, _)| is_word_char(next));
        if i > 0 && is_followed_by_word {
            text.push((' ', owner));
        }
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detokenize_matches_onnx_asr_spacing() {
        assert_eq!(detokenize(" Bonjour, je pense ."), "Bonjour, je pense.");
        assert_eq!(detokenize(" à amélior er"), "à amélior er");
        assert_eq!(detokenize(" l' équipe"), "l' équipe");
        assert_eq!(detokenize(""), "");
    }

    fn emitted(frame: usize, duration: usize) -> Emitted {
        Emitted {
            token: 0,
            frame,
            duration,
        }
    }

    #[test]
    fn words_take_their_time_from_their_first_and_last_token() {
        // " Bon" "jour" "," " ça" -> "Bonjour, ça": tokens 0..=2 spell the first word.
        let tokens = [emitted(4, 1), emitted(5, 2), emitted(7, 0), emitted(9, 3)];
        let pieces = [" Bon", "jour", ",", " ça"];
        let joined: Vec<(char, usize)> = pieces
            .iter()
            .enumerate()
            .flat_map(|(i, piece)| piece.chars().map(move |c| (c, i)))
            .collect();
        let words = words_of(&detokenize_owned(&joined), &tokens, 10.0);
        let texts: Vec<&str> = words.iter().map(|w| w.text.as_str()).collect();
        assert_eq!(texts, ["Bonjour,", "ça"]);
        // Frame 4 is 0.32 s into the framed input, 0.07 s after the lead silence.
        assert!((words[0].start_s - 0.07).abs() < 1e-4, "{:?}", words[0]);
        // The comma's duration 0 counts as one frame: frame 7 + 1.
        assert!((words[0].end_s - (8.0 * 0.08 - FRAME_S)).abs() < 1e-4);
        assert!((words[1].end_s - (12.0 * 0.08 - FRAME_S)).abs() < 1e-4);
        // Times never leave the input.
        assert_eq!(
            words_of(&detokenize_owned(&joined), &tokens, 0.1)[1].end_s,
            0.1
        );
        assert_eq!(frame_time(0, 5.0), 0.0);
    }

    /// Needs the Parakeet files on this Mac; skipped (with a note) otherwise.
    #[test]
    fn timed_words_match_the_plain_transcript_on_a_reference_clip() {
        let Ok(dir) = crate::models::parakeet_dir() else {
            eprintln!("skipped: no Parakeet model on this machine");
            return;
        };
        let reference = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../bench/reference");
        let mut parakeet = Parakeet::load(&dir).unwrap();
        for name in ["fr-sentence-rapport.wav", "fr-long-projet.wav"] {
            let samples = crate::audio::read_wav(&reference.join(name)).unwrap();
            let duration_s = samples.len() as f32 / crate::audio::SAMPLE_RATE as f32;
            // One encoder frame is 80 ms: the framed input's frame count says so.
            let (_, frames) = parakeet.run(&samples).unwrap();
            let framed_s = duration_s + 2.0 * FRAME_S;
            assert!(
                (frames as f32 * ENCODER_FRAME_S - framed_s).abs() < 2.0 * ENCODER_FRAME_S,
                "{name}: {frames} frames for {framed_s} s"
            );
            let text = parakeet.transcribe(&samples).unwrap();
            let words = parakeet.transcribe_timed(&samples).unwrap().unwrap();
            let joined: Vec<&str> = words.iter().map(|w| w.text.as_str()).collect();
            assert_eq!(joined.join(" "), text, "{name}");
            assert!(!words.is_empty(), "{name}");
            let mut previous = (0.0f32, 0.0f32);
            for word in &words {
                assert!(
                    word.start_s >= previous.0 && word.end_s >= previous.1,
                    "{word:?}"
                );
                assert!(word.end_s >= word.start_s, "{word:?}");
                previous = (word.start_s, word.end_s);
            }
            assert!(
                previous.1 <= duration_s,
                "{name}: {previous:?} > {duration_s}"
            );
        }
    }

    #[test]
    fn argmax_takes_the_first_maximum() {
        assert_eq!(argmax(&[0.1, 0.9, 0.9, -1.0]), 1);
    }
}

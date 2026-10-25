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
use crate::{Error, Transcriber};

const MAX_TOKENS_PER_STEP: usize = 10;
const WORD_START: char = '\u{2581}';
/// Digital silence put before and after every input. V1 measured it
/// (fcf7861): cut tight to its speech, a clip reaches Parakeet with no
/// silence around it, and Parakeet drops phrases or answers French in
/// English; 0.25 s cured that without losing a mixed-language clip. whisper
/// needs none: it pads every input to 30 s itself.
pub const FRAME_S: f32 = 0.25;

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

    fn decode(&mut self, frames: &[Vec<f32>]) -> Result<Vec<usize>, Error> {
        let mut states = self.zero_states();
        let mut tokens: Vec<usize> = Vec::new();
        let (mut t, mut emitted) = (0, 0);
        while t < frames.len() {
            let previous = tokens.last().copied().unwrap_or(self.blank);
            let (token, duration, next_states) = self.step(previous, &frames[t], &states)?;
            if token != self.blank {
                states = next_states;
                tokens.push(token);
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
}

impl Transcriber for Parakeet {
    fn name(&self) -> &'static str {
        "parakeet"
    }

    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
        let framed = crate::audio::padded(samples, FRAME_S, FRAME_S);
        let frames = self.encode(&framed)?;
        let tokens = self.decode(&frames)?;
        let joined: String = tokens
            .iter()
            .map(|&token| self.vocabulary[token].as_str())
            .collect();
        Ok(detokenize(&joined))
    }
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

/// onnx-asr's `re.sub(r"\A\s|\s\B|(\s)\b", ...)`: drop leading whitespace and
/// whitespace not followed by a word character, keep the rest as one space.
fn detokenize(joined: &str) -> String {
    let chars: Vec<char> = joined.chars().collect();
    let mut text = String::with_capacity(joined.len());
    for (i, &c) in chars.iter().enumerate() {
        if !c.is_whitespace() {
            text.push(c);
            continue;
        }
        let is_followed_by_word = chars.get(i + 1).is_some_and(|&next| is_word_char(next));
        if i > 0 && is_followed_by_word {
            text.push(' ');
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

    #[test]
    fn argmax_takes_the_first_maximum() {
        assert_eq!(argmax(&[0.1, 0.9, 0.9, -1.0]), 1);
    }
}

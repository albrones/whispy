//! Device audio → the 16 kHz mono the pipeline takes.
//!
//! Microphones on a Mac run at 44.1 or 48 kHz; V1 let PortAudio convert.
//! Here: average the channels, then band-limited (windowed-sinc) interpolation
//! with the cut-off just under the 8 kHz Nyquist of the output, so content
//! above it is filtered out instead of folding back onto speech.

use whispy_core::audio::SAMPLE_RATE;

/// Half-width of the sinc kernel, in input samples (scaled by the ratio when downsampling).
const KERNEL_HALF_WIDTH: f64 = 16.0;
/// Cut-off as a fraction of the output Nyquist, leaving room for the window's slope.
const CUTOFF: f64 = 0.92;

pub fn to_16k_mono(interleaved: &[f32], channels: usize, rate: u32) -> Vec<f32> {
    let mono = downmix(interleaved, channels);
    if rate == SAMPLE_RATE {
        return mono;
    }
    resample(&mono, rate, SAMPLE_RATE)
}

fn downmix(interleaved: &[f32], channels: usize) -> Vec<f32> {
    if channels <= 1 {
        return interleaved.to_vec();
    }
    interleaved
        .chunks_exact(channels)
        .map(|frame| frame.iter().sum::<f32>() / channels as f32)
        .collect()
}

fn resample(input: &[f32], from: u32, to: u32) -> Vec<f32> {
    let kernel = Kernel::new(from, to);
    let output_len = (input.len() as f64 / kernel.step).floor() as usize;
    (0..output_len)
        .map(|index| kernel.output_sample(input, 0, index, input.len()))
        .collect()
}

/// The windowed-sinc kernel from one rate to another.
struct Kernel {
    step: f64,
    cutoff: f64,
    half_width: f64,
}

impl Kernel {
    fn new(from: u32, to: u32) -> Kernel {
        let step = from as f64 / to as f64;
        // Downsampling widens the kernel and lowers the cut-off to the output's Nyquist.
        let scale = step.max(1.0);
        Kernel {
            step,
            cutoff: CUTOFF / scale,
            half_width: KERNEL_HALF_WIDTH * scale,
        }
    }

    /// The first input index output `index` reads.
    fn first_input(&self, index: usize) -> usize {
        (index as f64 * self.step - self.half_width).ceil().max(0.0) as usize
    }

    /// The last input index output `index` would read with unlimited input.
    fn last_input(&self, index: usize) -> usize {
        (index as f64 * self.step + self.half_width).floor() as usize
    }

    /// Output sample `index`. `input` holds the stream from absolute index
    /// `input_start`; `input_len` is the absolute length received so far.
    fn output_sample(
        &self,
        input: &[f32],
        input_start: usize,
        index: usize,
        input_len: usize,
    ) -> f32 {
        let center = index as f64 * self.step;
        let first = self.first_input(index);
        let last = self.last_input(index).min(input_len - 1);
        let mut sum = 0.0;
        for absolute in first..=last {
            let distance = absolute as f64 - center;
            sum += input[absolute - input_start] as f64
                * self.cutoff
                * sinc(distance * self.cutoff)
                * hann(distance / self.half_width);
        }
        sum as f32
    }
}

/// [`to_16k_mono`] while the recording goes on: each [`push`](StreamResampler::push)
/// returns the output samples the input so far fully determines, and
/// [`finish`](StreamResampler::finish) the rest. Put end to end, they are
/// exactly what `to_16k_mono` gives for the whole recording; only the input
/// the next samples still read is kept.
pub struct StreamResampler {
    channels: usize,
    rate: u32,
    kernel: Kernel,
    /// Mono input at the device rate, from absolute index `input_start`.
    mono: Vec<f32>,
    input_start: usize,
    /// Output samples returned so far.
    produced: usize,
}

impl StreamResampler {
    pub fn new(channels: usize, rate: u32) -> StreamResampler {
        StreamResampler {
            channels,
            rate,
            kernel: Kernel::new(rate, SAMPLE_RATE),
            mono: Vec::new(),
            input_start: 0,
            produced: 0,
        }
    }

    /// Takes device samples (interleaved) and returns the 16 kHz mono now ready.
    pub fn push(&mut self, interleaved: &[f32]) -> Vec<f32> {
        self.mono.extend(downmix(interleaved, self.channels));
        if self.rate == SAMPLE_RATE {
            return std::mem::take(&mut self.mono);
        }
        let input_len = self.input_start + self.mono.len();
        let mut ready = Vec::new();
        while self.kernel.last_input(self.produced) < input_len {
            ready.push(self.next_sample(input_len));
        }
        self.forget_read_input();
        ready
    }

    /// The last output samples, at the end of the recording.
    pub fn finish(&mut self) -> Vec<f32> {
        if self.rate == SAMPLE_RATE {
            return std::mem::take(&mut self.mono);
        }
        let input_len = self.input_start + self.mono.len();
        let output_len = (input_len as f64 / self.kernel.step).floor() as usize;
        let mut rest = Vec::new();
        while self.produced < output_len {
            rest.push(self.next_sample(input_len));
        }
        self.forget_read_input();
        rest
    }

    fn next_sample(&mut self, input_len: usize) -> f32 {
        let sample =
            self.kernel
                .output_sample(&self.mono, self.input_start, self.produced, input_len);
        self.produced += 1;
        sample
    }

    /// Drops the input no later output sample reads.
    fn forget_read_input(&mut self) {
        let needed = self.kernel.first_input(self.produced);
        let unneeded = needed.saturating_sub(self.input_start).min(self.mono.len());
        self.mono.drain(..unneeded);
        self.input_start += unneeded;
    }
}

fn sinc(x: f64) -> f64 {
    if x.abs() < 1e-9 {
        return 1.0;
    }
    let angle = std::f64::consts::PI * x;
    angle.sin() / angle
}

/// Hann window over -1..1.
fn hann(position: f64) -> f64 {
    if position.abs() >= 1.0 {
        return 0.0;
    }
    0.5 * (1.0 + (std::f64::consts::PI * position).cos())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(frequency: f64, rate: u32, seconds: f64) -> Vec<f32> {
        let count = (rate as f64 * seconds) as usize;
        (0..count)
            .map(|index| {
                (0.5 * (2.0 * std::f64::consts::PI * frequency * index as f64 / rate as f64).sin())
                    as f32
            })
            .collect()
    }

    /// RMS away from the edges, where the kernel runs out of input.
    fn middle_rms(samples: &[f32]) -> f32 {
        let middle = &samples[samples.len() / 4..samples.len() * 3 / 4];
        (middle.iter().map(|sample| sample * sample).sum::<f32>() / middle.len() as f32).sqrt()
    }

    #[test]
    fn speech_band_tones_keep_their_level_from_48k_and_44k1() {
        for rate in [48_000, 44_100] {
            let output = to_16k_mono(&tone(1_000.0, rate, 1.0), 1, rate);
            assert!(
                (output.len() as i64 - 16_000).abs() <= 1,
                "{rate}: {}",
                output.len()
            );
            let level = middle_rms(&output);
            assert!((level - 0.3536).abs() < 0.01, "{rate}: rms {level}");
        }
    }

    #[test]
    fn content_above_8k_does_not_fold_back() {
        // 12 kHz would alias to 4 kHz, in the middle of speech, without a filter.
        let output = to_16k_mono(&tone(12_000.0, 48_000, 1.0), 1, 48_000);
        assert!(middle_rms(&output) < 0.01, "rms {}", middle_rms(&output));
    }

    #[test]
    fn stereo_is_averaged() {
        let interleaved = [0.25, 0.75, -0.5, 0.0];
        assert_eq!(to_16k_mono(&interleaved, 2, SAMPLE_RATE), vec![0.5, -0.25]);
    }

    #[test]
    fn streaming_gives_exactly_the_one_shot_output() {
        let mut stereo = Vec::new();
        for sample in tone(440.0, 48_000, 1.3) {
            stereo.extend([sample, -sample * 0.5]);
        }
        for (channels, rate, input) in [
            (2, 48_000, stereo.clone()),
            (1, 44_100, tone(700.0, 44_100, 1.1)),
            (1, SAMPLE_RATE, tone(300.0, SAMPLE_RATE, 0.5)),
        ] {
            let whole = to_16k_mono(&input, channels, rate);
            // Odd block sizes, as a device delivers them (whole frames each).
            let mut streamed = StreamResampler::new(channels, rate);
            let mut output = Vec::new();
            for block in input.chunks(channels * 437) {
                output.extend(streamed.push(block));
            }
            output.extend(streamed.finish());
            assert_eq!(output, whole, "{channels} ch, {rate} Hz");
            // Only the input still to be read is kept, not the recording.
            assert!(streamed.mono.len() < 200, "{}", streamed.mono.len());
        }
    }

    #[test]
    fn empty_input_gives_empty_output() {
        assert!(to_16k_mono(&[], 1, 48_000).is_empty());
    }
}

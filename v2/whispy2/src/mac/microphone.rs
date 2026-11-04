//! The default input device, opened for each dictation (like V1), so a
//! microphone plugged in or chosen since the last one is the one used, and
//! macOS shows its recording indicator only while dictating.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream};

use crate::controller::{Capture, LevelSink};
use crate::feedback::{block_rms, LevelThrottle};
use crate::log;
use crate::resample;

#[derive(Default)]
pub struct Microphone {
    stream: Option<Stream>,
    /// Interleaved samples at the device's rate, filled by the audio thread.
    recorded: Arc<Mutex<Vec<f32>>>,
    channels: usize,
    rate: u32,
    /// The device of the last recording; kept after `stop` for the heard-nothing note.
    device_name: Option<String>,
    level_sink: Option<LevelSink>,
}

impl Microphone {
    pub fn new() -> Self {
        Microphone::default()
    }
}

impl Capture for Microphone {
    fn start(&mut self) -> Result<(), String> {
        let device = cpal::default_host()
            .default_input_device()
            .ok_or("no input device")?;
        let config = device
            .default_input_config()
            .map_err(|error| format!("input configuration: {error}"))?;
        self.device_name = device.name().ok();
        self.channels = config.channels() as usize;
        self.rate = config.sample_rate().0;
        self.recorded.lock().expect("audio buffer poisoned").clear();
        let sink = Arc::clone(&self.recorded);
        let on_error = |error| log::line(&format!("microphone: {error}"));
        // Each stream callback owns its throttle: 20 level updates a second, not one per block.
        let mut throttle = LevelThrottle::new();
        let level = self.level_sink.clone();
        let stream = match config.sample_format() {
            SampleFormat::F32 => device.build_input_stream(
                &config.into(),
                move |data: &[f32], _| {
                    sink.lock()
                        .expect("audio buffer poisoned")
                        .extend_from_slice(data);
                    push_level(&level, &mut throttle, data.iter().copied());
                },
                on_error,
                None,
            ),
            SampleFormat::I16 => device.build_input_stream(
                &config.into(),
                move |data: &[i16], _| {
                    let samples = data.iter().map(|sample| *sample as f32 / 32_768.0);
                    sink.lock()
                        .expect("audio buffer poisoned")
                        .extend(samples.clone());
                    push_level(&level, &mut throttle, samples);
                },
                on_error,
                None,
            ),
            other => {
                return Err(format!(
                    "the input device delivers {other} samples; expected f32 or i16"
                ))
            }
        }
        .map_err(|error| format!("opening the input stream: {error}"))?;
        stream
            .play()
            .map_err(|error| format!("starting the input stream: {error}"))?;
        self.stream = Some(stream);
        Ok(())
    }

    fn stop(&mut self) -> Vec<f32> {
        // Dropping the stream stops it; the buffer is complete afterwards.
        drop(self.stream.take());
        let recorded = std::mem::take(&mut *self.recorded.lock().expect("audio buffer poisoned"));
        resample::to_16k_mono(&recorded, self.channels, self.rate)
    }

    fn device_name(&self) -> Option<String> {
        self.device_name.clone()
    }

    fn set_level_sink(&mut self, sink: LevelSink) {
        self.level_sink = Some(sink);
    }
}

/// Pushes the block's RMS to the sink, at most 20 times a second. Runs on the
/// audio thread: the RMS is only computed when an update is due.
fn push_level(
    sink: &Option<LevelSink>,
    throttle: &mut LevelThrottle,
    samples: impl Iterator<Item = f32>,
) {
    if let Some(sink) = sink {
        if throttle.is_due(Instant::now()) {
            sink(block_rms(samples));
        }
    }
}

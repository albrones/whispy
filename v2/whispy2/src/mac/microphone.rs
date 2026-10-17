//! The default input device, opened for each dictation (like V1), so a
//! microphone plugged in or chosen since the last one is the one used, and
//! macOS shows its recording indicator only while dictating.

use std::sync::{Arc, Mutex};

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream};

use crate::controller::Capture;
use crate::resample;

#[derive(Default)]
pub struct Microphone {
    stream: Option<Stream>,
    /// Interleaved samples at the device's rate, filled by the audio thread.
    recorded: Arc<Mutex<Vec<f32>>>,
    channels: usize,
    rate: u32,
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
        self.channels = config.channels() as usize;
        self.rate = config.sample_rate().0;
        self.recorded.lock().expect("audio buffer poisoned").clear();
        let sink = Arc::clone(&self.recorded);
        let on_error = |error| eprintln!("[whispy2] microphone: {error}");
        let stream = match config.sample_format() {
            SampleFormat::F32 => device.build_input_stream(
                &config.into(),
                move |data: &[f32], _| {
                    sink.lock()
                        .expect("audio buffer poisoned")
                        .extend_from_slice(data)
                },
                on_error,
                None,
            ),
            SampleFormat::I16 => device.build_input_stream(
                &config.into(),
                move |data: &[i16], _| {
                    sink.lock()
                        .expect("audio buffer poisoned")
                        .extend(data.iter().map(|sample| *sample as f32 / 32_768.0))
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
}

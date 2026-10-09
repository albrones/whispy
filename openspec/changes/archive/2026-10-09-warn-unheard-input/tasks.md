## 1. Warn when the microphone heard nothing

- [x] 1.1 `AudioEngine`: `NOISE_FLOOR_PEAK_LEVEL` (0.1) and `MIN_UNHEARD_ALERT_S` (0.5), `unheard_input` names the device; log hint on the same threshold
- [x] 1.2 `Engine.stop_recording`: failure cue + `on_input_unheard` callbacks
- [x] 1.3 `Notifier.input_unheard`: Basso on macOS, freedesktop warning on Linux
- [x] 1.4 Menu bar: « Microphone heard nothing » notification
- [x] 1.5 Unit tests: `TestUnheardInput`, `TestInputUnheardSurfaced`

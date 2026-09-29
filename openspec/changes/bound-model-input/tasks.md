## 1. Model input ceiling

- [x] 1.1 Add `split_pcm` to `segmentation.py`: segmenter cuts, then fixed slices over the bound, lossless
- [x] 1.2 `AudioEngine.transcribe` routes clips over `MODEL_INPUT_MAX_S` through `_transcribe_in_pieces`
- [x] 1.3 Refuse (log, return None) a clip that is not 16 kHz mono int16 rather than feed it whole
- [x] 1.4 Unit tests: `TestSplitPcm` (bounded + lossless, leading silence), `TestModelInputCeiling` (no call over the bound)
- [x] 1.5 Real-model check: 180 s clip through `transcribe`, peak RSS measured

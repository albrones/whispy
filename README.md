# Whispy (Voice Dictation for macOS & Linux)

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE) [![Platform: macOS | Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20(X11)-lightgrey.svg)](#) &nbsp;·&nbsp; **[whispy-dun.vercel.app](https://whispy-dun.vercel.app)**

Whispy is a local voice dictation utility for macOS and Linux (X11). It runs
NVIDIA's Parakeet speech model on your own machine, so no audio or text ever
leaves your computer. Hold a trigger key (**Fn** on macOS, **Right Ctrl** on
Linux) to record and release it to type the transcription into the active
field, or switch on toggle mode to press once to start and once to stop.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash
```

On macOS this builds and installs the signed `Whispy.app`. On Linux, install the
system packages first (see the install guide below). If something does not
work afterwards, run `make doctor` from the repository for a diagnosis.

## Documentation

The full guides live on the website:

- [Install](https://whispy-dun.vercel.app/docs/install.html): step-by-step checklist for macOS and Linux
- [Troubleshooting](https://whispy-dun.vercel.app/docs/troubleshooting.html): symptom-driven fixes
- [Configuration](https://whispy-dun.vercel.app/docs/config.html): every setting, with a config builder
- [Usage](https://whispy-dun.vercel.app/docs/usage.html): dictation, toggle mode, the local API

## Platform support

Whispy runs on **macOS** and **Linux (X11)**. The OS-coupled seams sit behind a
ports-and-adapters layer (`src/whispy/platform/`) bound at runtime by
`platform.detect()`.

**Not supported in v1:** Wayland (global hotkey and synthetic input are
restricted by its security model; pick an "Xorg"/"X11" session at login),
Windows, native Linux packaging, and the floating overlay window on Linux
(state is shown through the tray instead).

## The model

Whispy ships one model: **`nvidia/parakeet-tdt-0.6b-v3`**, int8-quantized to
ONNX and run on CPU through [onnx-asr](https://github.com/istupakov/onnx-asr).
There is nothing to choose, so there is no model setting.

- **Download:** 639 MB, automatic on first use
- **Languages:** 25, detected automatically per utterance. Speech outside this
  set will not transcribe: Bulgarian, Croatian, Czech, Danish, Dutch, English,
  Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian,
  Lithuanian, Maltese, Polish, Portuguese, Romanian, Slovak, Slovenian,
  Spanish, Swedish, Russian, Ukrainian (see the
  [model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)).

## Contributing

Contributions and design input are welcome. Development setup, the test suite
and how to regenerate the docs are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is distributed under the **GPLv3** license. See the `LICENSE` file
for the full text.

The transcription model is a separate work under a different licence:
**`nvidia/parakeet-tdt-0.6b-v3`** is © NVIDIA Corporation, licensed
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Whispy does not
redistribute it: the weights are downloaded from the Hugging Face Hub on first
run and cached on your machine, so no model files ship in this repository or in
any release artifact. See `NOTICE` for the full attribution, including the ONNX
conversion Whispy loads.

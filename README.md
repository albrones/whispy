# Whispy (Voice Dictation for macOS & Linux)

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE) [![Platform: macOS | Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20(X11%20%26%20Wayland)-lightgrey.svg)](#) &nbsp;·&nbsp; **[whispy-dun.vercel.app](https://whispy-dun.vercel.app)**

Whispy is a local voice dictation app for macOS and Linux (X11 and Wayland),
written in Rust. It runs NVIDIA's Parakeet speech model on your own machine, so
no audio or text ever leaves your computer. Hold a trigger key (**Fn** on
macOS, **Right Ctrl** under X11, a compositor binding under Wayland) to record
and release it to type the transcription into the active field, or switch on
toggle mode to press once to start and once to stop.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash
```

It builds Whispy on your machine (the first build takes a few minutes),
installing Rust and cmake if they are missing:

- **macOS**: builds and signs `Whispy V2.app` into `/Applications` and launches it.
- **Linux**: installs the build tools with apt, dnf or pacman (through sudo),
  installs `~/.local/bin/whispy2` and runs it as the `systemd --user` unit
  `whispy2.service`, started with your session. On Omarchy it also links the
  dictation backend and the bar panel.

The app downloads its models (about 1.2 GB) on first launch. Run the command
again to update.

## Documentation

The full guides live on the website:

- [Install](https://whispy-dun.vercel.app/docs/install.html): step-by-step checklist for macOS and Linux
- [Troubleshooting](https://whispy-dun.vercel.app/docs/troubleshooting.html): symptom-driven fixes
- [Configuration](https://whispy-dun.vercel.app/docs/config.html): every setting, with a config builder
- [Usage](https://whispy-dun.vercel.app/docs/usage.html): dictation, toggle mode, the control socket

The app itself, its architecture and its bench are described in
[`v2/README.md`](v2/README.md).

## Platform support

Whispy runs on **macOS** (Apple Silicon and Intel) and **Linux** under **X11**
and **Wayland**.

**Wayland** (tested on Omarchy / Hyprland and sway): a Wayland client cannot
listen to a global key, so your compositor's key binding drives Whispy's
control socket (`whispy2 send start` on press, `whispy2 send stop` on release).
There is no tray icon; alerts arrive as desktop notifications. On **Omarchy**
the installer links the `omarchy-dictation-whispy` backend and the Whispy bar
panel; select the backend once, then pick the key in the panel:

```bash
omarchy-dictation-use whispy && hyprctl reload
```

**Not supported:** Windows, and Linux distribution packages (Whispy is built
from source by the installer).

## The model

Whispy transcribes with **`nvidia/parakeet-tdt-0.6b-v3`**, int8-quantized to
ONNX and run on CPU, and retries a dictation Parakeet heard nothing in with
**whisper small** (whisper.cpp). There is nothing to choose, so there is no
model setting.

- **Download:** about 1.2 GB, automatic on first launch, SHA-256 checked
- **Languages:** 25, detected automatically per utterance. Speech outside this
  set will not transcribe: Bulgarian, Croatian, Czech, Danish, Dutch, English,
  Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian,
  Lithuanian, Maltese, Polish, Portuguese, Romanian, Slovak, Slovenian,
  Spanish, Swedish, Russian, Ukrainian (see the
  [model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)).

## History

Whispy started as a Python app. Its last state is kept at the git tag
[`v1`](https://github.com/albrones/whispy/tree/v1); the Rust rewrite replaced
it on macOS, then on Linux.

## Contributing

Contributions and design input are welcome. Development setup, the tests
and how to regenerate the docs are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is distributed under the **GPLv3** license. See the `LICENSE` file
for the full text.

The transcription models are separate works under different licences:
**`nvidia/parakeet-tdt-0.6b-v3`** is © NVIDIA Corporation, licensed
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/), and whisper small is
© OpenAI, MIT-licensed. Whispy does not redistribute them: the weights are
downloaded from the Hugging Face Hub on first launch and cached on your
machine, so no model files ship in this repository or in any release artifact.
See `NOTICE` for the full attribution, including the ONNX conversion Whispy
loads.

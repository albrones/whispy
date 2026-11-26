#!/bin/bash
# Builds whispy2 for Linux in a container and runs the end-to-end checks of
# the Linux app: X11 (Xvfb) and Wayland (sway, headless). See README.md.
#
#   v2/whispy2/linux-e2e/run.sh <models-dir>
#
# <models-dir> holds `parakeet/` (the three Parakeet files and vocab.txt) and
# `ggml-small.bin`; nothing is downloaded. Needs Docker.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
models=$(cd "${1:?usage: run.sh <models-dir>}" && pwd)
image=whispy2-linux-e2e
docker build -q -t "$image" "$here" >/dev/null
run() {
  # Named volumes keep the build and the crates between runs. clang: GCC 12
  # cannot build whisper.cpp's ARM kernels (an aarch64 host).
  docker run --rm -v "$repo":/src:ro -v "$here":/e2e:ro -v "$models":/models:ro \
    -v whispy2-e2e-target:/target -v whispy2-e2e-cargo:/usr/local/cargo/registry \
    -e CARGO_TARGET_DIR=/target -e CC=clang -e CXX=clang++ -e LC_ALL=C.UTF-8 \
    -w /src/v2 "$image" bash -c "$1"
}
run 'cargo build --release --locked -p whispy2 && chmod -R a+rX /target/release'
echo "### X11: Right Ctrl, the tray icon, Quit (criteria 1 and 3)"
run '/e2e/x11.sh'
echo "### X11 without a tray host, X11 without an X server (criteria 3 and 4)"
run '/e2e/x11-degraded.sh'
echo "### Wayland: the control socket and enigo (criterion 2)"
# sway refuses to run as root.
run 'useradd -m e2e && su e2e -c /e2e/wayland.sh'

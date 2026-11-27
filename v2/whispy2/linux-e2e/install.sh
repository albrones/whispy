#!/bin/bash
# The installation check (card #54): on a fresh Debian with systemd, the
# one-line installer of the tag v1 installs Whispy V1, then the one-line
# installer of <ref> replaces it with V2, run as the systemd --user unit
# whispy2.service. A dictation of « Ajouter trois tests » with Right Ctrl
# (X11, Xvfb) types the text; after a new login (the user manager stopped and
# started again, the desktop session set up again) the unit is back and a
# second dictation types it again.
#
#   v2/whispy2/linux-e2e/install.sh <ref> <parakeet-hf-dir> <ggml-small.bin>
#
# <ref> is a branch or tag of github.com/albrones/whispy (the installer is
# fetched from raw.githubusercontent.com, as the website says). The models are
# copied in where V1 and V2 look for them, so neither downloads them:
# <parakeet-hf-dir> is V1's Hugging Face cache folder
# (~/.cache/huggingface/hub/models--istupakov--parakeet-tdt-0.6b-v3-onnx).
# Needs Docker with privileged containers (systemd runs as PID 1). The first
# run takes a while: V1's pip install, then rustup and the V2 build.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
ref=${1:?usage: install.sh <ref> <parakeet-hf-dir> <ggml-small.bin>}
parakeet=$(cd "${2:?parakeet HF dir}" && pwd)
whisper=$(cd "$(dirname "${3:?ggml-small.bin}")" && pwd)/$(basename "$3")
image=whispy-install-e2e
name=whispy-install-e2e
docker build -q -t "$image" "$here/install" >/dev/null
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  --tmpfs /run --tmpfs /run/lock \
  -v "$here":/e2e:ro -v "$parakeet":/models/hf:ro -v "$whisper":/models/ggml-small.bin:ro \
  "$image" >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker exec -e REF="$ref" "$name" bash /e2e/install/inside.sh

#!/usr/bin/env bash
# Regenerate the deterministic speech fixtures used by the live-driven
# transcription checks (`make validate`). These WAVs are committed so the same
# known audio is transcribed on macOS and Linux without a microphone.
#
# Requires macOS (`say` + `afconvert`). Run from the repo root:
#   bash tests/fixtures/audio/generate.sh
#
# Keep the spoken phrases in sync with the expected tokens asserted in
# tests/validation/harness.py (FIXTURES table).
set -euo pipefail
cd "$(dirname "$0")"

say -v Thomas "Test un deux trois, le test est fini" -o /tmp/_fr.aiff
afconvert /tmp/_fr.aiff -f WAVE -d LEI16@16000 -c 1 fr_speech.wav

say -v Alex "Testing one two three, the test is done" -o /tmp/_en.aiff
afconvert /tmp/_en.aiff -f WAVE -d LEI16@16000 -c 1 en_speech.wav

python3 - <<'PY'
import wave
with wave.open("silence.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 16000)  # 1 s of silence
PY

rm -f /tmp/_fr.aiff /tmp/_en.aiff
echo "Regenerated fr_speech.wav, en_speech.wav, silence.wav"

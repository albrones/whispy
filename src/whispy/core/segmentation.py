"""Voice-activity segmentation for streaming transcription.

Decides, frame by frame, when the current chunk of speech should be flushed for
transcription. Classification uses WebRTC VAD (``webrtcvad``) when available — a
gain-independent, well-tested voice detector that avoids the mid-word cuts a
naive energy threshold produces — and falls back to a simple energy gate when
the dependency is absent (so the app still imports and runs).

A chunk boundary is emitted when accumulated speech carrying at least
``min_speech_s`` of *voiced* audio is followed by at least ``pause_ms`` of
silence, OR when the buffered chunk reaches ``max_chunk_s`` (a forced flush so
run-on speech still streams). Audio is never dropped by the segmenter — it only
decides *where* to cut; the per-chunk VAD filter inside ``transcribe`` trims any
leading/trailing silence.
"""

import logging

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised indirectly; absence is the fallback path
    import webrtcvad
except Exception:  # pragma: no cover
    webrtcvad = None

# WebRTC VAD only accepts 8/16/32/48 kHz mono int16 in 10/20/30 ms frames.
# Capture is 16 kHz mono int16 (see audio.py), so a 30 ms frame is 480 samples.
SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480
FRAME_BYTES = FRAME_SAMPLES * 2  # int16 -> 960 bytes
# Energy-fallback speech gate (normalized RMS * 10, matching the capture level).
_FALLBACK_SPEECH_LEVEL = 0.04


def speech_duration_s(pcm: bytes, sample_rate: int = SAMPLE_RATE, aggressiveness: int = 2) -> float | None:
    """Total seconds of `pcm` that WebRTC VAD classifies as speech.

    Deliberately an absolute duration, not a speech/silence ratio: a ratio
    cannot tell one word inside a long key-hold from steady noise. Measured on
    an M1 Pro at aggressiveness 2, "okay" padded into a 10.6s hold is 6% speech
    frames and 2s of loud whitenoise is 6% too, while the *durations* are 0.66s
    against 0.09s. Across 125 noise realizations (white/brown/pink/fan, 2s and
    8s, all above the RMS gate) the worst was 0.12s; the shortest real word
    measured 0.33s.

    Returns None when VAD is unavailable or the audio cannot be framed, so an
    unmeasurable clip is transcribed rather than silently dropped.
    """
    if webrtcvad is None or sample_rate not in (8000, 16000, 32000, 48000):
        return None
    try:
        vad = webrtcvad.Vad(max(0, min(3, int(aggressiveness))))
    except Exception:  # pragma: no cover - defensive
        return None

    frame_bytes = sample_rate * FRAME_MS // 1000 * 2
    n_frames = len(pcm) // frame_bytes
    if n_frames == 0:
        return None

    speech = 0
    for i in range(n_frames):
        frame = pcm[i * frame_bytes : (i + 1) * frame_bytes]
        try:
            if vad.is_speech(frame, sample_rate):
                speech += 1
        except Exception:  # pragma: no cover - defensive
            return None
    return speech * FRAME_MS / 1000.0


class SpeechSegmenter:
    """Frame-based VAD segmenter fed raw 16 kHz mono int16 PCM.

    Usage from the capture callback / replay::

        if seg.feed(raw_block):   # True when a chunk boundary occurred
            flush_buffer_as_chunk()

    On stop, call ``flush_tail()``; if True, flush the remaining buffer.

    A pause closes a chunk only once the chunk holds ``min_speech_s`` of
    **voiced** audio. The quantity matters: each chunk is one independent model
    call, and a chunk carrying too little speech is resolved into the wrong
    language. Measured through the production transcription gates, an isolated
    "oui" chunk of 1.11 s total but 0.39 s voiced came back as English 5/5,
    while the same word with 0.5 s of preceding speech — 1.61 s total, 0.72 s
    voiced — was correct 5/5. Elapsed duration does not separate the two
    outcomes; voiced duration does. (An elapsed-time guard was also unreachable
    here: the pause condition already implies more elapsed time than any
    sensible minimum. That is the bug this replaced.) Below the threshold the
    segmenter simply keeps buffering, so the short word rides along with its
    neighbour — not emitting *is* the merge, since the caller already holds the
    audio.

    Three similarly-named thresholds live nearby and are different things:
    ``min_speech_s`` (here) gates *pause boundaries* on voiced seconds;
    ``min_chunk_s`` (config) is the engine's per-chunk *discard* duration, fed
    to ``transcribe`` as ``min_recording_duration``; ``MIN_SPEECH_DURATION_S``
    (``audio.py``, 0.20) is the per-chunk floor below which a clip is dropped as
    non-speech.
    """

    def __init__(
        self,
        pause_ms: float = 600,
        min_speech_s: float = 0.7,
        max_chunk_s: float = 12.0,
        aggressiveness: int = 2,
    ) -> None:
        self._pause_s = pause_ms / 1000.0
        self._min_speech_s = min_speech_s
        self._max_chunk_s = max_chunk_s
        self._frame_s = FRAME_MS / 1000.0

        self._vad = None
        if webrtcvad is not None:
            try:
                self._vad = webrtcvad.Vad(max(0, min(3, int(aggressiveness))))
            except Exception:  # pragma: no cover - defensive
                logger.warning("[segment] could not init webrtcvad; using energy fallback")
                self._vad = None
        else:
            logger.info("[segment] webrtcvad unavailable; using energy fallback")

        self._pending = bytearray()  # raw bytes awaiting a complete VAD frame
        self.reset_chunk()

    def reset_chunk(self) -> None:
        """Start a fresh (empty) chunk. The frame-alignment buffer is preserved."""
        self._have_speech = False
        self._buffered_s = 0.0
        self._speech_s = 0.0
        self._silence_s = 0.0

    @property
    def has_pending(self) -> bool:
        """True when the current chunk contains speech awaiting a flush."""
        return self._have_speech

    def _is_speech(self, frame: bytes) -> bool:
        if self._vad is not None:
            try:
                return self._vad.is_speech(frame, SAMPLE_RATE)
            except Exception:  # pragma: no cover - defensive
                return False
        # Energy fallback: normalized RMS * 10 (matches the capture-level gain).
        import numpy as np

        samples = np.frombuffer(frame, dtype=np.int16)
        if not samples.size:
            return False
        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 32768.0
        return rms * 10.0 > _FALLBACK_SPEECH_LEVEL

    def feed(self, raw: bytes) -> bool:
        """Consume a raw PCM block; return True if a chunk boundary occurred.

        Audio is always retained by the caller — this only decides cut points.
        Misclassifying the onset merely delays the first cut; it never drops audio.
        """
        self._pending.extend(raw)
        emit = False
        while len(self._pending) >= FRAME_BYTES:
            frame = bytes(self._pending[:FRAME_BYTES])
            del self._pending[:FRAME_BYTES]

            self._buffered_s += self._frame_s
            if self._is_speech(frame):
                self._have_speech = True
                self._speech_s += self._frame_s
                self._silence_s = 0.0
            else:
                self._silence_s += self._frame_s

            if self._have_speech and (
                (self._silence_s >= self._pause_s and self._speech_s >= self._min_speech_s)
                or self._buffered_s >= self._max_chunk_s
            ):
                emit = True
                self.reset_chunk()
        return emit

    def flush_tail(self) -> bool:
        """Return True if there is a pending speech chunk to flush on stop."""
        return self._have_speech

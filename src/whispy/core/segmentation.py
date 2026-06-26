"""Voice-activity segmentation for streaming transcription.

Decides, frame by frame, when the current chunk of speech should be flushed for
transcription. Classification uses WebRTC VAD (``webrtcvad``) when available — a
gain-independent, well-tested voice detector that avoids the mid-word cuts a
naive energy threshold produces — and falls back to a simple energy gate when
the dependency is absent (so the app still imports and runs).

A chunk boundary is emitted when accumulated speech is followed by at least
``pause_ms`` of silence, OR when the buffered chunk reaches ``max_chunk_s`` (a
forced flush so run-on speech still streams). Audio is never dropped by the
segmenter — it only decides *where* to cut; the per-chunk VAD filter inside
``transcribe`` trims any leading/trailing silence.
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


class SpeechSegmenter:
    """Frame-based VAD segmenter fed raw 16 kHz mono int16 PCM.

    Usage from the capture callback / replay::

        if seg.feed(raw_block):   # True when a chunk boundary occurred
            flush_buffer_as_chunk()

    On stop, call ``flush_tail()``; if True, flush the remaining buffer.
    """

    def __init__(
        self,
        pause_ms: float = 600,
        min_chunk_s: float = 0.4,
        max_chunk_s: float = 12.0,
        aggressiveness: int = 2,
    ) -> None:
        self._pause_s = pause_ms / 1000.0
        self._min_chunk_s = min_chunk_s
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
                self._silence_s = 0.0
            else:
                self._silence_s += self._frame_s

            if self._have_speech and (
                (self._silence_s >= self._pause_s and self._buffered_s >= self._min_chunk_s)
                or self._buffered_s >= self._max_chunk_s
            ):
                emit = True
                self.reset_chunk()
        return emit

    def flush_tail(self) -> bool:
        """Return True if there is a pending speech chunk to flush on stop."""
        return self._have_speech

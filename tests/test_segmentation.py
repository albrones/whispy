"""Tests for the VAD-based SpeechSegmenter (streaming chunk-boundary detector)."""

import sys
from pathlib import Path

import numpy as np

_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.segmentation import FRAME_BYTES, SAMPLE_RATE, SpeechSegmenter

# One 30 ms frame's worth of audio in each class. webrtcvad needs real spectral
# content for "speech"; a tone/noise reads as speech, zeros read as silence.
_FRAME_SAMPLES = FRAME_BYTES // 2


def _speech_block(n_frames=1):
    t = np.arange(_FRAME_SAMPLES * n_frames) / SAMPLE_RATE
    # Mix of tones approximating voiced energy; clearly "speech" to the VAD.
    sig = (np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 320 * t)) * 9000
    return sig.astype(np.int16).tobytes()


def _silence_block(n_frames=1):
    return bytes(FRAME_BYTES * n_frames)


class TestPauseEmit:
    def test_pause_after_speech_emits_a_chunk(self):
        seg = SpeechSegmenter(pause_ms=300, min_chunk_s=0.1, max_chunk_s=30.0)
        seg.feed(_speech_block(17))  # ~0.5s of speech
        # A pause past the threshold (0.3s) after speech must close the chunk.
        emitted = any(seg.feed(_silence_block(1)) for _ in range(20))
        assert emitted is True

    def test_short_speech_then_pause_does_not_emit_below_min_chunk(self):
        seg = SpeechSegmenter(pause_ms=150, min_chunk_s=2.0, max_chunk_s=10.0)
        seg.feed(_speech_block(3))  # ~0.09s, below min_chunk_s
        emitted = any(seg.feed(_silence_block(1)) for _ in range(20))
        assert emitted is False


class TestMaxLengthFlush:
    def test_run_on_speech_is_force_flushed(self):
        seg = SpeechSegmenter(pause_ms=600, min_chunk_s=0.4, max_chunk_s=1.0)
        # Continuous speech, no pause: must flush near max_chunk_s (1.0s ≈ 34 frames).
        emitted = seg.feed(_speech_block(40))
        assert emitted is True


class TestPureSilence:
    def test_silence_never_emits(self):
        seg = SpeechSegmenter(pause_ms=300, min_chunk_s=0.1)
        emitted = any(seg.feed(_silence_block(1)) for _ in range(100))
        assert emitted is False
        assert seg.has_pending is False


class TestOnsetNotClipped:
    """Recording that starts with speech (no lead-in) is detected immediately."""

    def test_speech_from_first_frame_sets_pending(self):
        seg = SpeechSegmenter(pause_ms=300, min_chunk_s=0.1)
        seg.feed(_speech_block(5))  # speech from the very first frames
        assert seg.has_pending is True


class TestTailFlush:
    def test_tail_pending_after_speech(self):
        seg = SpeechSegmenter()
        seg.feed(_speech_block(5))
        assert seg.flush_tail() is True

    def test_no_tail_after_pure_silence(self):
        seg = SpeechSegmenter()
        seg.feed(_silence_block(10))
        assert seg.flush_tail() is False


class TestFrameAlignment:
    def test_handles_blocks_not_aligned_to_frame_size(self):
        # Feed odd-sized blocks (not multiples of FRAME_BYTES); the segmenter
        # buffers the remainder and still detects speech across block edges.
        seg = SpeechSegmenter(pause_ms=300, min_chunk_s=0.1)
        speech = _speech_block(5)
        # Split into 100-byte chunks (not frame-aligned).
        for i in range(0, len(speech), 100):
            seg.feed(speech[i : i + 100])
        assert seg.has_pending is True


class TestEnergyFallback:
    def test_works_without_webrtcvad(self, monkeypatch):
        import whispy.core.segmentation as seg_mod

        monkeypatch.setattr(seg_mod, "webrtcvad", None)
        seg = SpeechSegmenter(pause_ms=300, min_chunk_s=0.1, max_chunk_s=10.0)
        assert seg._vad is None  # fell back to the energy gate
        seg.feed(_speech_block(10))
        assert seg.has_pending is True
        emitted = any(seg.feed(_silence_block(1)) for _ in range(20))
        assert emitted is True

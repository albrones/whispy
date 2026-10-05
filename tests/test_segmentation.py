"""Tests for the VAD-based SpeechSegmenter (streaming chunk-boundary detector)."""

import sys
from pathlib import Path

import numpy as np
import pytest

_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.segmentation import (
    FRAME_BYTES,
    HARD_MAX_FACTOR,
    LONE_WORD_PAUSE_S,
    SAMPLE_RATE,
    SOFT_FLUSH_GAP_S,
    SpeechSegmenter,
    speech_duration_s,
    speech_span_s,
    split_pcm,
    webrtcvad,
)

# `speech_duration_s` returns None without webrtcvad, and every caller treats that
# as "transcribe anyway". That is a supported configuration -- the segmenter ships
# an energy fallback for it -- so asserting on real VAD output has to skip there
# rather than fail. webrtcvad-wheels publishes manylinux x86_64/aarch64 and macOS
# wheels, so this skip should only ever fire on musl or an unusual architecture.
requires_vad = pytest.mark.skipif(webrtcvad is None, reason="webrtcvad not installed")

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
        seg = SpeechSegmenter(pause_ms=300, min_speech_s=0.05, max_chunk_s=30.0)
        seg.feed(_speech_block(17))  # ~0.5s of speech
        # A pause past the threshold (0.3s) after speech must close the chunk.
        emitted = any(seg.feed(_silence_block(1)) for _ in range(20))
        assert emitted is True

    def test_short_speech_then_pause_does_not_emit_below_min_speech(self):
        seg = SpeechSegmenter(pause_ms=150, min_speech_s=2.0, max_chunk_s=10.0)
        seg.feed(_speech_block(3))  # ~0.09s, below min_speech_s
        emitted = any(seg.feed(_silence_block(1)) for _ in range(20))
        assert emitted is False


class TestMaxLengthFlush:
    # `_voiced_block` (below) reads as speech on every frame; `_speech_block`
    # is only voiced for its first frames (the VAD adapts to a steady tone), so
    # it cannot stand in for run-on speech here.

    @requires_vad
    def test_run_on_speech_is_force_flushed_at_the_hard_cap(self):
        seg = SpeechSegmenter(pause_ms=600, max_chunk_s=1.0)
        # Continuous speech with no gap at all: nothing to cut on until the
        # unconditional ceiling (1.0s * HARD_MAX_FACTOR = 1.5s = 50 frames).
        assert seg.feed(_voiced_block(40)) is False  # past max_chunk_s, still speaking
        assert seg.feed(_voiced_block(15)) is True  # past the hard cap

    @requires_vad
    def test_past_max_chunk_the_cut_waits_for_a_short_gap(self):
        # Measured on a live dictation: a cut at an arbitrary frame lands
        # mid-word and the two halves come back as "mais" / "Mais". Past
        # max_chunk_s the segmenter therefore cuts on the first short gap.
        seg = SpeechSegmenter(pause_ms=600, max_chunk_s=1.0)
        assert seg.feed(_voiced_block(40)) is False  # 1.2s: past max_chunk_s, no gap yet
        gap_frames = int(round(SOFT_FLUSH_GAP_S / 0.03))
        # WebRTC VAD has a few frames of hangover after speech, so the gap is
        # counted from when the VAD flips, not from the first zero frame.
        hangover_allowance = 8
        cut_at = next((i for i in range(1, gap_frames + hangover_allowance + 1) if seg.feed(_silence_block(1))), None)
        assert cut_at is not None  # a short gap is enough once past max_chunk_s
        assert cut_at >= gap_frames  # ...but not before the gap is real

    @requires_vad
    def test_gap_before_max_chunk_does_not_cut(self):
        # The soft rule only arms once the chunk is long; a 200 ms gap in a
        # short chunk is an ordinary between-words breath, not a boundary.
        seg = SpeechSegmenter(pause_ms=600, max_chunk_s=5.0)
        seg.feed(_voiced_block(20))  # 0.6s
        gap_frames = int(round(SOFT_FLUSH_GAP_S / 0.03)) + 2
        assert not any(seg.feed(_silence_block(1)) for _ in range(gap_frames))

    def test_hard_cap_is_a_multiple_of_max_chunk(self):
        assert HARD_MAX_FACTOR > 1.0


class TestPureSilence:
    def test_silence_never_emits(self):
        seg = SpeechSegmenter(pause_ms=300, min_speech_s=0.05)
        emitted = any(seg.feed(_silence_block(1)) for _ in range(100))
        assert emitted is False
        assert seg.has_pending is False


class TestOnsetNotClipped:
    """Recording that starts with speech (no lead-in) is detected immediately."""

    def test_speech_from_first_frame_sets_pending(self):
        seg = SpeechSegmenter(pause_ms=300, min_speech_s=0.05)
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
        seg = SpeechSegmenter(pause_ms=300, min_speech_s=0.05)
        speech = _speech_block(5)
        # Split into 100-byte chunks (not frame-aligned).
        for i in range(0, len(speech), 100):
            seg.feed(speech[i : i + 100])
        assert seg.has_pending is True


class TestEnergyFallback:
    def test_works_without_webrtcvad(self, monkeypatch):
        import whispy.core.segmentation as seg_mod

        monkeypatch.setattr(seg_mod, "webrtcvad", None)
        seg = SpeechSegmenter(pause_ms=300, min_speech_s=0.05, max_chunk_s=10.0)
        assert seg._vad is None  # fell back to the energy gate
        seg.feed(_speech_block(10))
        assert seg.has_pending is True
        emitted = any(seg.feed(_silence_block(1)) for _ in range(20))
        assert emitted is True


def _voiced_block(n_frames=1):
    """A harmonic stack, which webrtcvad reads as speech across every frame.

    `_speech_block` above is enough for the segmenter (one voiced frame opens a
    chunk), but only ~18% of its frames read as speech, so it cannot be used to
    assert on a *duration*.
    """
    t = np.arange(_FRAME_SAMPLES * n_frames) / SAMPLE_RATE
    sig = sum(np.sin(2 * np.pi * (120 * h) * t) / h for h in range(1, 12)) * 8000
    return sig.astype(np.int16).tobytes()


@requires_vad
class TestSpeechDuration:
    """`speech_duration_s` — the absolute-duration metric behind the speech gate."""

    def test_speech_measures_roughly_its_own_length(self):
        got = speech_duration_s(_voiced_block(17))  # 17 frames = 0.51s
        assert got is not None
        assert 0.45 <= got <= 0.51

    def test_silence_measures_zero(self):
        assert speech_duration_s(_silence_block(30)) == 0.0

    def test_one_word_in_a_long_hold_is_not_penalized(self):
        """The reason the gate measures duration and not a speech/silence ratio.

        A word surrounded by a long key-hold is ~6% voiced frames — the same
        ratio as steady noise — but its voiced *duration* is unchanged, so the
        buried word must measure at least as much as the tightly-cropped one.
        """
        tight = speech_duration_s(_voiced_block(17))
        buried = speech_duration_s(_silence_block(100) + _voiced_block(17) + _silence_block(100))
        assert buried >= tight

    def test_returns_none_without_webrtcvad(self, monkeypatch):
        """Fails open: an unmeasurable clip must be transcribed, not dropped."""
        import whispy.core.segmentation as seg_mod

        monkeypatch.setattr(seg_mod, "webrtcvad", None)
        assert speech_duration_s(_voiced_block(17)) is None

    def test_returns_none_for_an_unsupported_sample_rate(self):
        assert speech_duration_s(_voiced_block(17), sample_rate=44100) is None

    def test_returns_none_when_shorter_than_one_frame(self):
        assert speech_duration_s(_voiced_block(1)[:100]) is None


class TestVoicedSpeechGate:
    """A pause closes a chunk only once it holds `min_speech_s` of voiced audio.

    `_voiced_block` reads as speech on every frame, so n frames is exactly
    n * 30 ms of voiced audio — the quantity under test.
    """

    @staticmethod
    def _pause(seg, frames=30):
        """Feed silence one frame at a time; return True on the first boundary."""
        return any(seg.feed(_silence_block(1)) for _ in range(frames))

    @requires_vad
    def test_below_threshold_pause_does_not_emit_and_speech_is_carried_over(self):
        seg = SpeechSegmenter(pause_ms=600, min_speech_s=0.7, max_chunk_s=30.0)
        seg.feed(_voiced_block(10))  # 0.30s voiced, below 0.7s
        assert self._pause(seg) is False
        # The chunk is still open, so the next utterance joins it: the two are
        # emitted together as ONE chunk, which is how the short word reaches the
        # model with context.
        seg.feed(_voiced_block(20))  # 0.30 + 0.60 = 0.90s voiced
        assert self._pause(seg) is True

    @requires_vad
    def test_at_threshold_pause_emits(self):
        seg = SpeechSegmenter(pause_ms=600, min_speech_s=0.7, max_chunk_s=30.0)
        seg.feed(_voiced_block(30))  # 0.90s voiced
        assert self._pause(seg) is True

    @requires_vad
    def test_old_elapsed_time_guard_was_unreachable(self):
        """Regression: the previous rule could not block this boundary.

        It compared `_buffered_s` (total buffered seconds, silence included)
        against `min_chunk_s` = 0.4. By the time the pause condition held,
        `_silence_s` was already >= 0.6, so `_buffered_s` >= 0.6 > 0.4 always —
        the guard was unreachable, and this chunk (0.39s voiced, the measured
        wrong-language case) was emitted alone.
        """
        seg = SpeechSegmenter(pause_ms=600, min_speech_s=0.7, max_chunk_s=30.0)
        seg.feed(_voiced_block(13))  # 0.39s voiced
        assert self._pause(seg) is False
        assert seg._buffered_s > 0.4  # what the old rule was comparing

    @requires_vad
    def test_max_chunk_still_force_flushes_below_threshold(self):
        # Audio can never be held indefinitely for want of voiced seconds. The
        # trailing silence is itself the gap the soft rule cuts on.
        seg = SpeechSegmenter(pause_ms=600, min_speech_s=0.7, max_chunk_s=1.0)
        seg.feed(_voiced_block(10))  # 0.30s voiced, below the threshold
        assert self._pause(seg, frames=40) is True  # flushed once past max_chunk_s

    @requires_vad
    def test_lone_word_is_emitted_once_the_speaker_has_clearly_stopped(self):
        # Live-drive case: "test" alone, nothing after it. Held for context it
        # waited for the 12 s cut and drowned in the RMS gate. Past
        # LONE_WORD_PAUSE_S of silence there is no next utterance to ride with.
        seg = SpeechSegmenter(pause_ms=600, min_speech_s=0.7, max_chunk_s=30.0)
        seg.feed(_voiced_block(13))  # 0.39s voiced, below the threshold
        frames_to_lone = int(round(LONE_WORD_PAUSE_S / 0.03))
        assert self._pause(seg, frames=frames_to_lone - 2) is False  # still held
        assert self._pause(seg, frames=12) is True  # emitted once the silence is long

    @requires_vad
    def test_lone_word_pause_is_longer_than_the_ordinary_pause(self):
        assert LONE_WORD_PAUSE_S > 0.6  # otherwise min_speech_s would never bind

    @requires_vad
    def test_tail_flush_ignores_the_threshold(self):
        # A dictation that is entirely one short word is still emitted at stop.
        seg = SpeechSegmenter(pause_ms=600, min_speech_s=0.7, max_chunk_s=30.0)
        seg.feed(_voiced_block(5))  # 0.15s voiced
        assert self._pause(seg) is False
        assert seg.flush_tail() is True


class TestSpeechSpan:
    """`speech_span_s` — where the speech starts and ends, for trimming."""

    @requires_vad
    def test_span_brackets_the_voiced_frames(self):
        first, last, voiced = speech_span_s(_silence_block(100) + _voiced_block(17) + _silence_block(50))
        # WebRTC VAD carries a few frames of hangover after speech, so `last`
        # and `voiced` may run up to ~0.2 s past the 17 voiced frames.
        assert first == pytest.approx(3.0, abs=0.06)
        assert 3.51 - 0.06 <= last <= 3.51 + 0.2
        assert 0.51 - 0.06 <= voiced <= 0.51 + 0.2

    @requires_vad
    def test_pure_silence_is_an_empty_span(self):
        assert speech_span_s(_silence_block(30)) == (0.0, 0.0, 0.0)

    @requires_vad
    def test_duration_is_the_span_voiced_total(self):
        pcm = _silence_block(10) + _voiced_block(17) + _silence_block(10)
        assert speech_duration_s(pcm) == speech_span_s(pcm)[2]

    def test_returns_none_without_webrtcvad(self, monkeypatch):
        import whispy.core.segmentation as seg_mod

        monkeypatch.setattr(seg_mod, "webrtcvad", None)
        assert speech_span_s(_voiced_block(17)) is None


class TestSplitPcm:
    """split_pcm bounds every piece and never drops or reorders audio."""

    MAX_S = 30.0

    def _assert_bounded_and_lossless(self, pcm):
        pieces = split_pcm(pcm, self.MAX_S)
        assert b"".join(pieces) == pcm
        assert all(len(p) <= self.MAX_S * SAMPLE_RATE * 2 for p in pieces)
        return pieces

    def test_run_on_speech_is_cut_at_the_segmenter_ceiling(self):
        pieces = self._assert_bounded_and_lossless(_speech_block(int(90 / 0.03)))
        assert len(pieces) > 3  # the segmenter's own ceiling, not the 30 s slice

    def test_long_leading_silence_is_sliced(self):
        # The segmenter never cuts before the first speech frame.
        self._assert_bounded_and_lossless(_silence_block(int(75 / 0.03)) + _speech_block(100))

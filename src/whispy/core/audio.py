"""Audio recording and transcription logic.

Captures audio via the cross-platform ``sounddevice`` (PortAudio) backend and
transcribes via Parakeet (onnx-asr), integrating with the state machine for
lifecycle management. The same recorder serves macOS and Linux.
"""

import glob
import logging
import os
import sys
import tempfile
import threading
import uuid
import wave
from collections.abc import Callable
from typing import Any

import numpy as np

from .segmentation import SpeechSegmenter, speech_duration_s
from .state_machine import StateMachine

# ``sounddevice`` loads libportaudio at import time, which is absent on headless
# CI boxes. Guard the import (mirroring the Quartz pattern) so the module always
# imports; capture degrades gracefully when the backend is unavailable.
try:
    import sounddevice as sd
except Exception:  # pragma: no cover - depends on the host audio stack
    sd = None

logger = logging.getLogger(__name__)

# Capture format — 16 kHz mono 16-bit PCM WAV. Kept identical to the previous
# sox output so the transcription path is unaffected.
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16

# Below this normalized RMS a clip is treated as silence and never transcribed.
#
# Parakeet does not hallucinate the way Whisper did (no training-corpus
# artifacts, no repetition loops), but it does invent short conversational
# fillers on near-silence. Measured on this machine: pure digital silence and a
# realistic quiet-room noise floor produced "Yeah.", "Okay.", "Mm-hmm.", "No."
# and "Thank you." at RMS values up to 0.00065, while real speech measured 0.147
# and above -- a 220x gap. 0.005 sits far above every observed false positive and
# far below any real dictation.
#
# An energy gate rather than a phrase blocklist on purpose: "Okay." and "No."
# are legitimate one-word dictations, so filtering by text would delete real
# speech. Energy never looks at what was said.
SILENCE_RMS_THRESHOLD = 0.005

# Minimum seconds of VAD-voiced audio required before a clip reaches the model.
#
# The RMS gate above only catches *near-silence*. Non-speech that is merely loud
# -- a noisy room, a fan, 50 Hz mains hum -- clears it (0.010-0.035 measured
# against the 0.005 threshold) and reaches the model, where roughly 3% of
# realizations come back as a filler. Voiced-frame duration separates the two
# populations with a 2.7x margin: across 125 noise realizations the worst
# carried 0.12s of voiced frames, while the shortest real one-word dictation
# ("non", 0.40s of audio) carried 0.33s. 0.20s sits between them.
#
# A duration and not a speech/silence ratio: a ratio cannot distinguish one word
# inside a long key-hold (6% voiced at 10.6s) from steady noise (6% voiced), and
# holding the trigger while thinking is normal use.
#
# Known ceiling: webrtcvad has an energy floor, so it only tells noise from
# speech while the noise is quiet. Past roughly 0.04 normalized RMS it labels
# steady noise 100% voiced and this gate stops discriminating -- measured across
# white/pink/lowpassed noise, every level from vol 0.2 up reads as fully voiced.
# That band is left to the model, which returned "" for all 15 such clips. The
# gate is aimed at where the leaks actually were (0.010-0.035 RMS, 0.09-0.18s
# voiced); a real fix for louder rooms would need a speech-vs-noise classifier,
# not a louder threshold.
MIN_SPEECH_DURATION_S = 0.20

RECORDING_PATH = os.path.join(tempfile.gettempdir(), "whispy.wav")


def _open_recording_wav(path: str) -> wave.Wave_write:
    """Create (or truncate) a recording WAV with 0o600 permissions.

    Recording WAVs briefly hold captured voice audio; a plain
    ``wave.open(path, "wb")`` creates the file under the process umask (often
    ~0644 on Linux), leaving it world-readable in the shared temp dir. Creating
    the file via ``os.open`` with an explicit mode first closes that window —
    the OS ignores the mode argument on an already-existing file, so the
    subsequent ``wave.open`` (which just opens it normally) never widens the
    permissions back. Returns a normal ``Wave_write`` so callers keep using it
    exactly like ``wave.open`` (including ``with``).
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(fd)
    return wave.open(path, "wb")


def _cleanup_stale_recordings() -> None:
    """Best-effort removal of leftover whispy-*.wav files from a prior crash.

    Each recording writes to a unique ``whispy-<uuid>.wav`` path (see
    ``_new_recording_path``); a crash — or a transcription exception before
    the run_transcription ``finally``-cleanup fix — could leave one behind
    indefinitely, holding recorded voice audio. Runs once per AudioEngine
    startup and must never fail startup itself.
    """
    try:
        for stale in glob.glob(os.path.join(tempfile.gettempdir(), "whispy-*.wav")):
            try:
                os.remove(stale)
            except OSError:
                pass
    except OSError:
        pass


# Minimum file size (bytes) indicating audio was actually captured.
_MIN_RECORDING_SIZE = 5120  # 5 KB
# Timeout for waiting for the capture stream to start delivering audio (seconds)
_RECORDING_READY_TIMEOUT = 2.0


class AudioEngine:
    """Manages audio recording and transcription operations.

    Capture goes through ``sounddevice`` (PortAudio): a ``RawInputStream``
    delivers int16 frames to a callback that streams them into the WAV file at
    ``RECORDING_PATH``. Integrates with the StateMachine to ensure proper
    lifecycle: IDLE -> RECORDING (start) -> TRANSCRIBING (stop) -> IDLE.
    """

    def __init__(self, state_machine: StateMachine):
        # Best-effort: clear out any whispy-*.wav left by a prior crash before
        # this instance starts writing its own — never fails startup.
        _cleanup_stale_recordings()

        self._sm = state_machine
        self._stream = None
        self._wave = None
        # Guards every access to ``self._wave``: the PortAudio callback thread
        # writes/creates it while stop() (hotkey thread) closes and nulls it.
        self._wave_lock = threading.Lock()
        # Each recording writes to its own unique path so a recording started
        # while a previous transcription is still reading cannot corrupt or
        # delete the in-use file. Defaults to the shared path until first start.
        self._recording_path = RECORDING_PATH
        self._frames_written = 0
        self._ready = threading.Event()
        # Error message when the last start() could not open a capture stream
        # (after the refresh-and-retry sequence); None when capture is healthy.
        # The engine reads this to notify the user instead of failing silently.
        self._capture_failed: str | None = None
        # Live input level (0.0-1.0) computed from the capture callback so the
        # waveform UI can visualize it WITHOUT opening a second microphone
        # stream — two concurrent input streams on the same CoreAudio device
        # make capture deliver silent (all-zero) buffers.
        self._level = 0.0

        # --- Streaming / incremental transcription ---
        # When enabled, the capture callback segments the live stream on silence
        # (and a max length) and hands each chunk to ``_on_chunk`` for the engine
        # to transcribe + inject while recording continues. Off by default: the
        # legacy single-file path is used verbatim.
        self._streaming = False
        self._on_chunk: Callable[[str], None] | None = None
        self._seg_kwargs: dict[str, float] = {}
        self._segmenter: SpeechSegmenter | None = None
        self._chunk_buf = bytearray()

    def configure_streaming(
        self,
        enabled: bool,
        on_chunk: Callable[[str], None] | None = None,
        *,
        pause_ms: float = 600,
        min_chunk_s: float = 0.4,
        max_chunk_s: float = 12.0,
        aggressiveness: int = 2,
    ) -> None:
        """Enable/disable live segmentation and register the chunk sink.

        ``on_chunk`` is called (from the capture callback thread, and from
        ``stop()`` for the tail) with the path of a self-contained WAV to
        transcribe. The engine wires it to its chunk queue.
        """
        self._streaming = bool(enabled)
        self._on_chunk = on_chunk
        self._seg_kwargs = {
            "pause_ms": pause_ms,
            "min_chunk_s": min_chunk_s,
            "max_chunk_s": max_chunk_s,
            "aggressiveness": aggressiveness,
        }

    def _emit_chunk(self) -> None:
        """Write the buffered chunk to a unique WAV and hand it to the sink.

        Called from the capture callback (on a boundary) and from ``stop()`` (the
        tail). No-op when the buffer is empty. Errors are contained by the caller.
        """
        if not self._chunk_buf:
            return
        path = self._new_recording_path()
        with _open_recording_wav(path) as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(bytes(self._chunk_buf))
        self._chunk_buf = bytearray()
        if self._on_chunk is not None:
            self._on_chunk(path)

    def _feed_segmenter(self, raw: bytes) -> None:
        """Drive the VAD segmenter with one captured block.

        All audio is retained in the chunk buffer; the segmenter only decides
        when to cut. The segmenter resets its own timing on a boundary.
        """
        if self._segmenter is None:
            return
        self._chunk_buf.extend(raw)
        if self._segmenter.feed(raw):
            self._emit_chunk()

    def segment_pcm(
        self,
        pcm: bytes,
        *,
        pause_ms: float = 600,
        min_chunk_s: float = 0.4,
        max_chunk_s: float = 12.0,
        aggressiveness: int = 2,
        block_frames: int = 1600,
    ) -> list[str]:
        """Replay raw int16 PCM through the live segmenter; return chunk WAV paths.

        Deterministic seam for validation: drives the SAME ``_feed_segmenter`` /
        ``_emit_chunk`` (and the same VAD segmenter) the capture callback uses, so
        a fixture WAV exercises streaming segmentation end to end without a
        microphone. Each emitted chunk is written to a unique WAV; the caller
        transcribes and cleans them up. Restores any live capture state.
        """
        paths: list[str] = []
        prev_sink, prev_seg, prev_buf = (self._on_chunk, self._segmenter, self._chunk_buf)
        self._on_chunk = paths.append
        self._segmenter = SpeechSegmenter(
            pause_ms=pause_ms,
            min_chunk_s=min_chunk_s,
            max_chunk_s=max_chunk_s,
            aggressiveness=aggressiveness,
        )
        self._chunk_buf = bytearray()
        step = block_frames * CHANNELS * SAMPLE_WIDTH
        try:
            for i in range(0, len(pcm), step):
                raw = pcm[i : i + step]
                if not raw:
                    continue
                self._feed_segmenter(raw)
            if self._segmenter.flush_tail():
                self._emit_chunk()
        finally:
            self._on_chunk, self._segmenter, self._chunk_buf = (prev_sink, prev_seg, prev_buf)
        return paths

    def start(self) -> bool:
        """Start recording audio. Returns False if already recording.

        Opens a ``sounddevice`` capture stream and waits until it begins
        delivering audio (the device cold-start delay) before returning, so the
        first recording is not empty. The wait terminates on first audio, on a
        stream-open failure, or on a readiness timeout — never blocking forever.
        """
        if not self._sm.start_recording():
            return False

        self._frames_written = 0
        self._ready = threading.Event()
        self._capture_failed = None
        with self._wave_lock:
            self._wave = None
        # Fresh unique path for this recording (isolates it from any in-flight
        # transcription still reading the previous recording).
        self._recording_path = self._new_recording_path()
        self._level = 0.0

        # Fresh segmenter + empty chunk buffer for a streaming recording.
        if self._streaming:
            self._segmenter = SpeechSegmenter(**self._seg_kwargs)
            self._chunk_buf = bytearray()

        if sd is None:
            logger.warning("[audio] sounddevice backend unavailable — cannot capture audio.")
            self._ready.set()
            return True

        def _callback(indata, frames, _time_info, status) -> None:
            # The whole body is guarded: an exception here runs inside the
            # PortAudio C callback, where it is undefined behavior. Log and
            # contain it (a dropped frame), never raise into the backend.
            try:
                if status:
                    logger.debug("[audio] stream status: %s", status)
                raw = bytes(indata)
                # Update the live level for the waveform: normalized RMS of the
                # int16 block (gain 10, matching the old AudioLevelMonitor). Done
                # first so the streaming segmenter can consume the same level.
                samples = np.frombuffer(raw, dtype=np.int16)
                if samples.size:
                    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 32768.0
                    self._level = min(rms * 10.0, 1.0)

                if self._streaming:
                    # Segment the live stream: buffer the chunk, and on a silence/
                    # length boundary write it out and hand it to the sink. No
                    # whole-file WAV is written in streaming mode.
                    self._feed_segmenter(raw)
                else:
                    # Legacy path: open the WAV lazily on first audio so a failed
                    # stream never truncates a prior recording. Serialize handle
                    # access against stop() via the lock.
                    with self._wave_lock:
                        if self._wave is None:
                            self._wave = _open_recording_wav(self._recording_path)
                            self._wave.setnchannels(CHANNELS)
                            self._wave.setsampwidth(SAMPLE_WIDTH)
                            self._wave.setframerate(SAMPLE_RATE)
                        self._wave.writeframes(raw)
                self._frames_written += frames
            except Exception:
                logger.exception("[audio] capture callback error — frame dropped")
            finally:
                self._ready.set()

        # Re-enumerate devices so the stream targets the CURRENT system default
        # input — the list PortAudio cached at daemon startup goes stale when a
        # Bluetooth headset connects/disconnects or the machine wakes from sleep.
        self._refresh_devices()
        try:
            self._stream = self._open_stream(_callback)
        except Exception:
            # The device set may have changed between refresh and open (e.g.
            # Bluetooth negotiation completing mid-start): refresh once more and
            # retry a single time.
            try:
                self._refresh_devices()
                self._stream = self._open_stream(_callback)
            except Exception as exc:
                # No device / device busy: stop the readiness wait and warn rather
                # than block. The recording will be empty; transcription discards
                # it. The engine reads capture_failed to notify the user.
                logger.warning("[audio] Could not open capture stream: %s", exc)
                self._capture_failed = str(exc)
                self._stream = None
                self._ready.set()
                return True

        self._wait_for_recording_ready()
        return True

    def _refresh_devices(self) -> None:
        """Force PortAudio to re-scan audio devices (terminate + re-initialize).

        PortAudio freezes its device list at initialization; in a long-running
        daemon the cached default input goes stale after a device change and
        opening the stream fails with PaErrorCode -9986. sounddevice exposes no
        public re-scan, so the underscore pair is the established refresh path
        (pinned by a unit test). Must never run while a stream is open — start()
        is guarded by the state machine and this app opens no other PortAudio
        stream (the level meter reads from the capture stream). A refresh
        failure degrades to the stale list rather than aborting the recording.
        """
        if sd is None:
            return
        try:
            sd._terminate()
            sd._initialize()
        except Exception as exc:
            logger.warning("[audio] device list refresh failed: %s", exc)

    def _open_stream(self, callback: Callable):
        """Open and start a capture stream on the current default input device."""
        stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=callback,
        )
        stream.start()
        return stream

    @property
    def capture_failed(self) -> str | None:
        """Error message when the last start() could not open a stream, else None."""
        return self._capture_failed

    def _new_recording_path(self) -> str:
        """Return a unique temp WAV path for one recording."""
        return os.path.join(tempfile.gettempdir(), f"whispy-{uuid.uuid4().hex}.wav")

    @property
    def recording_path(self) -> str:
        """Path of the most recently started recording (the file to transcribe)."""
        return self._recording_path

    def _wait_for_recording_ready(self) -> None:
        """Wait until the stream delivers its first audio, or the timeout fires.

        ``_ready`` is set by the stream callback on the first frames (or
        immediately on a failed/absent backend), so this never blocks
        indefinitely — at worst it returns after the readiness timeout.
        """
        if not self._ready.wait(timeout=_RECORDING_READY_TIMEOUT):
            logger.warning(
                "[audio] Timeout waiting for recording to start — "
                "audio device may not be ready. First recording may be empty."
            )

    def get_level(self) -> float:
        """Return the live input level (0.0-1.0) from the capture stream.

        Drives the recording waveform from the single capture stream, so the UI
        never opens a competing microphone stream. Returns 0.0 when idle.
        """
        return self._level

    def stop(self) -> bool:
        """Stop recording and transition to TRANSCRIBING. Returns False if not recording."""
        self._level = 0.0
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("[audio] stream close error: %s", exc)
            self._stream = None

        # Streaming tail: the stream is stopped, so the callback can no longer
        # touch the buffer; flush any pending speech as the final chunk.
        if self._streaming and self._segmenter is not None and self._segmenter.flush_tail():
            try:
                self._emit_chunk()
            except Exception:
                logger.exception("[audio] tail chunk flush failed")
            self._segmenter.reset_chunk()

        with self._wave_lock:
            if self._wave is not None:
                try:
                    self._wave.close()
                except Exception as exc:
                    logger.debug("[audio] wave close error: %s", exc)
                self._wave = None

        if os.path.exists(self._recording_path):
            try:
                size = os.path.getsize(self._recording_path)
                if size < _MIN_RECORDING_SIZE:
                    logger.warning(
                        f"[audio] Recording file too small ({size} bytes) — "
                        "the audio device may not have been ready when recording stopped. "
                        "Try pressing the trigger key again once the daemon is awake."
                    )
            except OSError:
                pass

        return self._sm.stop_recording()

    def transcribe(
        self,
        audio_path: str,
        model: Any | None,
        min_recording_duration: float = 0.3,
    ) -> str | None:
        """Transcribe an audio file. Returns None if there is nothing to inject.

        No decoder-tuning arguments are accepted or forwarded. Parakeet is a
        transducer: it detects language itself (forcing one made the previous
        backend translate rather than recognize), decodes greedily, carries no
        cross-call context, and exposes no prompt/hotword biasing channel.
        Custom vocabulary is applied afterwards, in text cleaning.
        """
        if model is None:
            print(
                "[audio] Model not loaded, skipping transcription",
                file=sys.stderr,
            )
            return None

        # A misclick-length clip has nothing in it worth a decoder pass. The
        # model returns empty text for silence, so this guard saves time rather
        # than suppressing hallucination as it did under Whisper.
        duration = self._get_audio_duration(audio_path)
        if duration is not None and duration < min_recording_duration:
            logger.info(
                "[audio] Recording too short (%.2fs < %.1fs) — discarding.",
                duration,
                min_recording_duration,
            )
            return None

        # Near-silent audio must never reach the model. Parakeet invents short
        # backchannel fillers on it -- "Yeah.", "Okay.", "Mm-hmm.", "No.",
        # "Thank you." -- which would be typed into the user's active field.
        rms = self._get_audio_rms(audio_path)
        if rms is not None and rms < SILENCE_RMS_THRESHOLD:
            logger.info(
                "[audio] Recording is near-silent (RMS %.6f < %.4f) — discarding.",
                rms,
                SILENCE_RMS_THRESHOLD,
            )
            return None

        # Non-speech loud enough to clear the RMS gate -- a noisy room, a fan, a
        # mains hum -- still reaches the model, and roughly 3% of the time
        # (3/100 realizations measured) Parakeet answers it with a filler
        # ("Yeah.", "Ha ha ha."). VAD closes that: the same clips carry at most
        # 0.12s of speech frames against 0.33s for the shortest real word.
        if not self._carries_speech(audio_path):
            return None

        try:
            text = (model.recognize(audio_path) or "").strip()
            return text if text else None
        except Exception as exc:
            print(f"[audio] Transcription error: {exc}", file=sys.stderr)
            return None

    def _carries_speech(self, audio_path: str) -> bool:
        """True when the clip holds enough VAD-detected speech to be worth decoding.

        Fails open: an unreadable file, a non-16-bit clip, or a missing
        ``webrtcvad`` all return True, so a clip that cannot be measured is
        transcribed rather than dropped. Losing a real dictation is worse than
        typing an occasional filler.
        """
        try:
            with wave.open(audio_path, "rb") as wf:
                if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
                    return True
                rate = wf.getframerate()
                pcm = wf.readframes(wf.getnframes())
        except (OSError, wave.Error):
            return True

        speech_s = speech_duration_s(pcm, sample_rate=rate)
        if speech_s is None:
            return True
        if speech_s < MIN_SPEECH_DURATION_S:
            logger.info(
                "[audio] No speech detected (%.2fs < %.2fs of voiced frames) — discarding.",
                speech_s,
                MIN_SPEECH_DURATION_S,
            )
            return False
        return True

    def _get_audio_rms(self, audio_path: str) -> float | None:
        """Root-mean-square amplitude of a WAV, normalized to 0.0-1.0.

        Returns None when the file cannot be measured, so an unmeasurable clip
        is transcribed rather than silently dropped.
        """
        try:
            with wave.open(audio_path, "rb") as wf:
                width = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())
        except (OSError, wave.Error):
            return None

        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
        if dtype is None or not raw:
            return None

        samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
        if samples.size == 0:
            return None
        if width == 1:  # 8-bit PCM is unsigned, centred on 128
            samples = (samples - 128.0) / 128.0
        else:
            samples /= float(np.iinfo(dtype).max)
        return float(np.sqrt(np.mean(samples**2)))

    def _get_audio_duration(self, audio_path: str) -> float | None:
        """Detect audio file duration in seconds using the wave module.

        Falls back to None if the file cannot be read as WAV.
        """
        try:
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except (OSError, wave.Error):
            pass
        return None

    def cleanup_audio_file(self, audio_path: str | None = None) -> None:
        """Remove the temporary audio file after transcription.

        Defaults to the current recording's path when no path is given.
        """
        target = audio_path if audio_path is not None else self._recording_path
        try:
            if target and os.path.exists(target):
                os.remove(target)
        except OSError:
            pass

    @property
    def is_recording(self) -> bool:
        return self._sm.is_recording

    @property
    def is_transcribing(self) -> bool:
        return self._sm.is_transcribing

"""Audio recording and transcription logic.

Captures audio via the cross-platform ``sounddevice`` (PortAudio) backend and
transcribes via Parakeet (onnx-asr), integrating with the state machine for
lifecycle management. The same recorder serves macOS and Linux.
"""

import glob
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import wave
from collections.abc import Callable
from typing import Any

import numpy as np

from .segmentation import SpeechSegmenter, speech_span_s, split_pcm
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
# The gate compares the threshold against the loudest window of this length,
# not the whole-clip mean. Measured on a live dictation: one word ("test",
# ~0.4 s) held by the segmenter for context and then flushed inside 10 s of
# silence averaged 0.00496 — under the gate by 1% — and was discarded. The
# mean scales the word by sqrt(voiced / total); the loudest 0.5 s window is
# the word itself. A near-silent clip has no loud window, so it still fails.
PEAK_RMS_WINDOW_S = 0.5

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
# Both this threshold and SILENCE_RMS_THRESHOLD were measured on macOS, against
# `say` synthesis and one microphone. `TestSpeechGateAgainstCommittedAudio` keeps
# them honest elsewhere: it checks the margin against the committed *recordings*
# and runs in the default tier, which CI runs on ubuntu as well as macOS. What
# remains unmeasured is a real Linux microphone at a different capture gain --
# webrtcvad classifies gain-independently but has an energy floor, so a very
# quiet input could fall under it.
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

# Before the model call, a clip is cut down to its outermost VAD-speech frames
# plus this margin on each side. Silence around an utterance is not neutral to
# Parakeet: measured with `scripts/asr-bench/probe_lone_word.py` (3 words x 6
# voices x 2 levels), an isolated word followed by 0.6 s of silence was
# recognized 12/15, by 5 s 4-6/15, by 10 s 3-5/15; trimmed to its voiced span
# the same clips came back 10-12/15 whatever the tail. A lone word that the
# segmenter holds for `LONE_WORD_PAUSE_S` (or the soft cut) always arrives
# with seconds of silence attached, and was coming back empty 7 times out of 9
# on a live drive. Internal silences are kept: only the ends are cut.
TRIM_MARGIN_S = 0.3

# Longest clip handed to the model in one call; a longer file is split first
# (see ``_transcribe_in_pieces``). Measured with the int8 model on the pinned
# CPU provider (M1 Pro): peak RSS 1268 MB at 8 s, 1476 MB at 30 s, 1688 MB at
# 60 s, 3503 MB at 180 s -- memory and latency grow with clip length. The same
# 180 s clip under CoreML reached 25 GB and took the whole machine down
# (userspace watchdog panic, 2026-09-29). Streaming chunks never come near
# this; it bounds the whole-file paths (streaming disabled, /transcribe-file).
MODEL_INPUT_MAX_S = 30.0
# Rewrite the clip only when it saves at least this much; a clip that already
# starts and ends on speech goes to the model as is.
TRIM_MIN_GAIN_S = 0.25

RECORDING_PATH = os.path.join(tempfile.gettempdir(), "whispy.wav")

# A clip lost to the model (see "Lost speech" in ``transcribe``) is kept here so
# it can be replayed (scripts/replay_lost.py) instead of guessed at. Only losses
# are kept -- never a clip that was transcribed -- and only the newest
# LOST_CLIPS_KEPT, so the folder holds a few minutes of voice at most.
LOST_CLIPS_DIR = os.path.expanduser("~/.whispy/lost")
LOST_CLIPS_KEPT = 20


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


def _keep_lost_clip(audio_path: str) -> str:
    """Copy a lost clip into LOST_CLIPS_DIR, drop the oldest beyond LOST_CLIPS_KEPT, return the copy's name.

    Returns "nothing" when the copy fails: keeping the clip is a diagnostic aid,
    so its failure is logged and never stops the transcription path.
    """
    # Nanoseconds in the name: chunks of one recording can be lost within the
    # same second, and pruning relies on names sorting in loss order.
    now_ns = time.time_ns()
    name = f"lost-{time.strftime('%Y%m%d-%H%M%S', time.localtime(now_ns // 1_000_000_000))}-{now_ns % 1_000_000_000:09d}.wav"
    try:
        os.makedirs(LOST_CLIPS_DIR, mode=0o700, exist_ok=True)
        shutil.copyfile(audio_path, os.path.join(LOST_CLIPS_DIR, name))
        kept = sorted(glob.glob(os.path.join(LOST_CLIPS_DIR, "lost-*.wav")))
        for oldest in kept[:-LOST_CLIPS_KEPT]:
            os.remove(oldest)
    except OSError:
        logger.exception("[audio] could not keep lost clip %s in %s", audio_path, LOST_CLIPS_DIR)
        return "nothing"
    return name


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
        # Per-recording capture-health counters, reported once by stop().
        # Incremented from the PortAudio callback, which is why they are plain
        # ints and not log calls: measuring must not add work to the thread
        # whose overruns are being measured.
        self._xruns = 0
        self._xruns_after_emit = 0
        self._max_emit_ms = 0.0
        self._emitted_last_block = False
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
        self._on_chunk: Callable[[str, str], None] | None = None
        self._seg_kwargs: dict[str, float] = {}
        self._segmenter: SpeechSegmenter | None = None
        self._chunk_buf = bytearray()

    def configure_streaming(
        self,
        enabled: bool,
        on_chunk: Callable[[str, str], None] | None = None,
        *,
        pause_ms: float = 600,
        min_speech_s: float = 0.7,
        max_chunk_s: float = 8.0,
        soft_gap_ms: float = 350,
        aggressiveness: int = 2,
    ) -> None:
        """Enable/disable live segmentation and register the chunk sink.

        ``on_chunk`` is called (from the capture callback thread, and from
        ``stop()`` for the tail) with the path of a self-contained WAV to
        transcribe and the boundary reason that closed it (``SENTENCE`` or
        ``CONTINUATION``). The engine wires it to its chunk queue; the reason is
        what lets the engine join chunk texts without inventing a sentence break.
        """
        self._streaming = bool(enabled)
        self._on_chunk = on_chunk
        self._seg_kwargs = {
            "pause_ms": pause_ms,
            "min_speech_s": min_speech_s,
            "max_chunk_s": max_chunk_s,
            "soft_gap_ms": soft_gap_ms,
            "aggressiveness": aggressiveness,
        }

    def _emit_chunk(self, reason: str) -> None:
        """Write the buffered chunk to a unique WAV and hand it to the sink.

        Called from the capture callback (on a boundary) and from ``stop()`` (the
        tail). ``reason`` is the segmenter's boundary reason and travels with the
        chunk. No-op when the buffer is empty. Errors are contained by the caller.
        """
        if not self._chunk_buf:
            return
        path = self._new_recording_path()
        # Timed because this write runs on the capture callback thread: if it
        # overruns the block deadline the driver drops the next frames, which
        # is audio lost exactly at a chunk boundary. Counters only, no I/O.
        started = time.perf_counter()
        with _open_recording_wav(path) as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(bytes(self._chunk_buf))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if elapsed_ms > self._max_emit_ms:
            self._max_emit_ms = elapsed_ms
        self._emitted_last_block = True
        self._chunk_buf = bytearray()
        if self._on_chunk is not None:
            self._on_chunk(path, reason)

    def _feed_segmenter(self, raw: bytes) -> None:
        """Drive the VAD segmenter with one captured block.

        All audio is retained in the chunk buffer; the segmenter only decides
        when to cut. The segmenter resets its own timing on a boundary.
        """
        if self._segmenter is None:
            return
        self._chunk_buf.extend(raw)
        reason = self._segmenter.feed(raw)
        if reason:
            self._emit_chunk(reason)

    def segment_pcm(
        self,
        pcm: bytes,
        *,
        pause_ms: float = 600,
        min_speech_s: float = 0.7,
        max_chunk_s: float = 8.0,
        soft_gap_ms: float = 350,
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
        self._on_chunk = lambda path, _reason: paths.append(path)
        self._segmenter = SpeechSegmenter(
            pause_ms=pause_ms,
            min_speech_s=min_speech_s,
            max_chunk_s=max_chunk_s,
            soft_gap_ms=soft_gap_ms,
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
            tail_reason = self._segmenter.flush_tail()
            if tail_reason:
                self._emit_chunk(tail_reason)
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
        self._xruns = 0
        self._xruns_after_emit = 0
        self._max_emit_ms = 0.0
        self._emitted_last_block = False
        self._ready = threading.Event()
        self._capture_failed = None
        with self._wave_lock:
            self._wave = None
        # Fresh unique path for this recording (isolates it from any in-flight
        # transcription still reading the previous recording).
        self._recording_path = self._new_recording_path()
        self._level = 0.0
        self._peak_level = 0.0

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
                    # Counted, never logged: this runs inside the PortAudio
                    # callback, and a logging call here does file I/O on the
                    # very thread whose overruns we are trying to measure.
                    # The totals are reported once, by stop().
                    self._xruns += 1
                    if self._emitted_last_block:
                        self._xruns_after_emit += 1
                self._emitted_last_block = False
                raw = bytes(indata)
                # Update the live level for the waveform: normalized RMS of the
                # int16 block (gain 10, matching the old AudioLevelMonitor). Done
                # first so the streaming segmenter can consume the same level.
                samples = np.frombuffer(raw, dtype=np.int16)
                if samples.size:
                    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 32768.0
                    self._level = min(rms * 10.0, 1.0)
                    if self._level > self._peak_level:
                        self._peak_level = self._level

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

        # One line per recording naming what is being listened to. A recording
        # that captures only the room's noise floor is otherwise
        # indistinguishable in the log from one where the user said nothing
        # (live drive, 2026-09-14: 84 s of RMS 0.0036, no device recorded).
        logger.info("[audio] capture open: input %s, stream %d Hz", self._describe_input_device(), SAMPLE_RATE)
        self._wait_for_recording_ready()
        return True

    def _describe_input_device(self) -> str:
        """Human-readable current default input device, for the capture log line."""
        try:
            info = sd.query_devices(kind="input")
            return f"{info['name']!r} (native {float(info['default_samplerate']):.0f} Hz)"
        except Exception as exc:  # no device, backend quirk -- never fail a recording over a log line
            return f"unknown ({exc})"

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
            # Peak level is the waveform's own scale (normalized RMS x10, so the
            # near-silence gate sits at 0.05). Speech reads 0.2 and above; a
            # whole recording under the gate means the microphone did not hear
            # the user -- lid closed, stale input after sleep, wrong device.
            seconds = self._frames_written / SAMPLE_RATE
            hint = (
                ""
                if self._peak_level >= SILENCE_RMS_THRESHOLD * 10
                else " -- at the noise floor, check the input device"
            )
            logger.info("[audio] capture closed: %.1fs, peak level %.3f%s", seconds, self._peak_level, hint)
            # Capture health for this recording. A dropped block is audio the
            # model never sees, so it is a loss, not a statistic -- and
            # `after a chunk write` is the number that says whether writing the
            # chunk WAV on the callback thread is what caused it.
            if self._xruns:
                logger.warning(
                    "[audio] capture xruns: %d dropped block(s), %d right after a chunk write; "
                    "slowest chunk write %.1f ms",
                    self._xruns,
                    self._xruns_after_emit,
                    self._max_emit_ms,
                )
            elif self._max_emit_ms:
                logger.info("[audio] capture clean; slowest chunk write %.1f ms", self._max_emit_ms)

        # Streaming tail: the stream is stopped, so the callback can no longer
        # touch the buffer; flush any pending speech as the final chunk.
        tail_reason = self._segmenter.flush_tail() if (self._streaming and self._segmenter is not None) else None
        if tail_reason:
            try:
                self._emit_chunk(tail_reason)
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
        if duration is not None and duration > MODEL_INPUT_MAX_S:
            return self._transcribe_in_pieces(audio_path, model, min_recording_duration)

        # Near-silent audio must never reach the model. Parakeet invents short
        # backchannel fillers on it -- "Yeah.", "Okay.", "Mm-hmm.", "No.",
        # "Thank you." -- which would be typed into the user's active field.
        rms = self._get_peak_rms(audio_path)
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
        span = self._speech_span(audio_path)
        if span is not None and not self._span_carries_speech(span):
            return None

        # Silence around the utterance makes the model return nothing (see
        # TRIM_MARGIN_S). Cut to the voiced span; the trimmed file is the
        # model's input only, the caller still owns and deletes `audio_path`.
        model_path = self._trim_to_speech(audio_path, span, duration)
        trimmed = model_path != audio_path
        try:
            text = (model.recognize(model_path) or "").strip()
            if not text and trimmed:
                # Every gate passed, so the clip did carry voice. Trimming is the
                # only transformation applied between the gates and the model
                # call, which makes it the first suspect -- so try once more on
                # the original. One retry, not a loop: the cost stays bounded and
                # a second empty answer is information, not a reason to keep
                # trying. A clip the model already saw untrimmed is not retried.
                logger.info(
                    "[audio] Empty result on the trimmed clip — retrying on the untrimmed %.2fs original.",
                    duration or 0.0,
                )
                text = (model.recognize(audio_path) or "").strip()
        except Exception:
            # Logged, not printed: the bundled app has no stderr sink, so a
            # print here is invisible in a live drive.
            logger.exception("[audio] Transcription error")
            return None
        finally:
            if trimmed:
                self.cleanup_audio_file(model_path)
        if not text:
            # Speech that vanished, not a routine non-speech discard: the gates
            # above log theirs at INFO, this one is a loss and carries the three
            # measurements that would explain it, plus the kept clip, so the
            # next investigation starts with numbers and audio instead of a re-drive.
            logger.warning(
                "[audio] Lost speech: the model returned no text for a %.2fs clip that cleared every gate "
                "(peak RMS %s, voiced %s, kept as %s).",
                duration or 0.0,
                "unknown" if rms is None else f"{rms:.6f}",
                "unknown" if span is None else f"{span[2]:.2f}s",
                _keep_lost_clip(audio_path),
            )
            return None
        # Successes are counted next to losses in the same log; the text itself
        # stays out of it.
        logger.info("[audio] Transcribed a %.2fs clip (%d characters).", duration or 0.0, len(text))
        return text

    def _transcribe_in_pieces(self, audio_path: str, model: Any, min_recording_duration: float) -> str | None:
        """Transcribe a clip longer than ``MODEL_INPUT_MAX_S`` piece by piece.

        Each piece goes back through ``transcribe`` -- same gates, same trim --
        and is short enough not to recurse again.
        """
        with wave.open(audio_path, "rb") as wf:
            params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
            pcm = wf.readframes(wf.getnframes())
        if params != (CHANNELS, SAMPLE_WIDTH, SAMPLE_RATE):
            logger.error(
                "[audio] Cannot split %s: (channels, sample width, rate) is %s, expected %s — not transcribed.",
                audio_path,
                params,
                (CHANNELS, SAMPLE_WIDTH, SAMPLE_RATE),
            )
            return None
        texts: list[str] = []
        for piece in split_pcm(pcm, MODEL_INPUT_MAX_S):
            path = self._new_recording_path()
            with _open_recording_wav(path) as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(SAMPLE_WIDTH)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(piece)
            try:
                text = self.transcribe(path, model, min_recording_duration)
            finally:
                self.cleanup_audio_file(path)
            if text:
                texts.append(text)
        # ponytail: plain space join; streaming's boundary-aware punctuation join
        # is the upgrade if long whole-file dictation becomes a real path.
        return " ".join(texts) or None

    def _speech_span(self, audio_path: str) -> tuple[float, float, float] | None:
        """``(first_s, last_s, voiced_s)`` of the clip's VAD speech, or None if unmeasurable.

        None (unreadable file, non-16-bit or non-mono clip, missing
        ``webrtcvad``) means "fail open": the caller transcribes the clip
        untrimmed rather than dropping it.
        """
        try:
            with wave.open(audio_path, "rb") as wf:
                if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
                    return None
                rate = wf.getframerate()
                pcm = wf.readframes(wf.getnframes())
        except (OSError, wave.Error):
            return None
        return speech_span_s(pcm, sample_rate=rate)

    def _span_carries_speech(self, span: tuple[float, float, float]) -> bool:
        """The speech gate on a measured span; logs the discard reason."""
        speech_s = span[2]
        if speech_s < MIN_SPEECH_DURATION_S:
            logger.info(
                "[audio] No speech detected (%.2fs < %.2fs of voiced frames) — discarding.",
                speech_s,
                MIN_SPEECH_DURATION_S,
            )
            return False
        return True

    def _carries_speech(self, audio_path: str) -> bool:
        """True when the clip holds enough VAD-detected speech to be worth decoding.

        Fails open: an unmeasurable clip returns True, so it is transcribed
        rather than dropped. Losing a real dictation is worse than typing an
        occasional filler.
        """
        span = self._speech_span(audio_path)
        return True if span is None else self._span_carries_speech(span)

    def _trim_to_speech(
        self,
        audio_path: str,
        span: tuple[float, float, float] | None,
        duration: float | None,
    ) -> str:
        """Write a copy of the clip cut to its voiced span (+ TRIM_MARGIN_S) and return its path.

        Returns ``audio_path`` itself when the span is unknown, when trimming
        would save less than TRIM_MIN_GAIN_S, or when the copy cannot be
        written -- the model then sees the original, never nothing.
        """
        if span is None or duration is None or span[2] <= 0.0:
            return audio_path
        start = max(0.0, span[0] - TRIM_MARGIN_S)
        end = min(duration, span[1] + TRIM_MARGIN_S)
        if (duration - (end - start)) < TRIM_MIN_GAIN_S:
            return audio_path
        trimmed = f"{audio_path}.trim.wav"
        try:
            with wave.open(audio_path, "rb") as src:
                rate = src.getframerate()
                width = src.getsampwidth()
                channels = src.getnchannels()
                src.setpos(int(start * rate))
                frames = src.readframes(int((end - start) * rate))
            with wave.open(trimmed, "wb") as dst:
                dst.setnchannels(channels)
                dst.setsampwidth(width)
                dst.setframerate(rate)
                dst.writeframes(frames)
        except (OSError, wave.Error):
            logger.warning("[audio] could not trim %s; transcribing it whole", audio_path)
            return audio_path
        logger.debug("[audio] trimmed %.2fs -> %.2fs before the model", duration, end - start)
        return trimmed

    def _get_peak_rms(self, audio_path: str, window_s: float = PEAK_RMS_WINDOW_S) -> float | None:
        """Highest normalized RMS over any ``window_s`` window of a WAV.

        The near-silence gate's metric. Unlike the whole-clip mean it does not
        dilute one word in a long silence (see PEAK_RMS_WINDOW_S). A clip
        shorter than the window is measured whole. Returns None when the file
        cannot be measured, so an unmeasurable clip is transcribed.
        """
        loaded = self._load_normalized(audio_path)
        if loaded is None:
            return None
        samples, rate = loaded
        window = max(1, int(window_s * rate))
        if samples.size <= window:
            return float(np.sqrt(np.mean(samples**2)))
        # Sliding mean of squares via a cumulative sum; hop of 1/5 window.
        sq = np.concatenate(([0.0], np.cumsum(samples**2)))
        hop = max(1, window // 5)
        starts = np.arange(0, samples.size - window + 1, hop)
        means = (sq[starts + window] - sq[starts]) / window
        return float(np.sqrt(means.max()))

    def _load_normalized(self, audio_path: str) -> tuple[np.ndarray, int] | None:
        """WAV samples as float64 in -1.0..1.0 plus the sample rate; None if unreadable."""
        try:
            with wave.open(audio_path, "rb") as wf:
                width = wf.getsampwidth()
                rate = wf.getframerate()
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
            samples = samples / float(np.iinfo(dtype).max)
        return samples, rate

    def _get_audio_rms(self, audio_path: str) -> float | None:
        """Root-mean-square amplitude of a WAV, normalized to 0.0-1.0.

        Whole-clip mean; kept for calibration checks. The gate itself uses
        ``_get_peak_rms``. Returns None when the file cannot be measured.
        """
        loaded = self._load_normalized(audio_path)
        if loaded is None:
            return None
        samples, _rate = loaded
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

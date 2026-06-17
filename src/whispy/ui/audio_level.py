"""Thread-safe audio level monitor using the system microphone.

Reads real-time audio from the default input device and exposes
a smoothed RMS amplitude value (0.0-1.0) for visualization.
"""

import logging
import threading
from typing import Any

import sounddevice as sd

from .level_math import rms_to_level

logger = logging.getLogger(__name__)

# Smoothing factor for exponential moving average (0.0-1.0, higher = smoother)
_DEFAULT_SMOOTHING = 0.85
# Block size for audio callback (lower = lower latency)
_DEFAULT_BLOCK_SIZE = 1024
# Default audio sample rate
_DEFAULT_SAMPLE_RATE = 16000


class AudioLevelMonitor:
    """Monitors real-time microphone audio level via sounddevice.

    Runs a background thread that continuously reads the default microphone
    input and computes RMS amplitude. The smoothed level is exposed via
    get_level() for consumption by the visualization at any frame rate.
    """

    def __init__(
        self,
        smoothing: float = _DEFAULT_SMOOTHING,
        block_size: int = _DEFAULT_BLOCK_SIZE,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._smoothing = smoothing
        self._block_size = block_size
        self._sample_rate = sample_rate
        self._current_level: float = 0.0
        self._smoothed_level: float = 0.0
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Start monitoring the microphone. Returns False if already started."""
        if self._running:
            return False
        self._running = True
        try:
            self._stream = sd.InputStream(
                device=None,  # default device
                channels=1,
                samplerate=self._sample_rate,
                blocksize=self._block_size,
                callback=self._audio_callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            logger.error("[audio-level] Failed to start microphone: %s", exc)
            self._running = False
            return False
        return True

    def stop(self) -> None:
        """Stop monitoring and release the microphone device."""
        if not self._running:
            return
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except sd.PortAudioError:
                pass
            self._stream = None

    def _audio_callback(self, indata: Any, frames: int, time_info, status: sd.CallbackFlags) -> None:
        """Compute RMS amplitude from audio input and apply smoothing."""
        if status:
            return
        # Compute RMS of the channel (numpy on the raw block stays here); the
        # normalize + smoothing step is the pure rms_to_level helper.
        rms = float((indata**2).mean()) ** 0.5
        with self._lock:
            self._smoothed_level = rms_to_level(rms, self._smoothed_level, self._smoothing)

    def get_level(self) -> float:
        """Return the current smoothed audio level (0.0-1.0).

        Returns 0.0 if the monitor is not running.
        """
        with self._lock:
            return self._smoothed_level

    @property
    def is_running(self) -> bool:
        return self._running

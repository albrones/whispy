"""Audio recording and transcription logic.

Handles audio capture via sox and transcription via faster-whisper,
integrating with the state machine for lifecycle management.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from .state_machine import State, StateMachine

RECORDING_PATH = os.path.join(tempfile.gettempdir(), "whispy.wav")


class AudioEngine:
    """Manages audio recording and transcription operations.

    Integrates with the StateMachine to ensure proper lifecycle:
    IDLE -> RECORDING (start) -> TRANSCRIBING (stop) -> IDLE (complete)
    """

    def __init__(self, state_machine: StateMachine):
        self._sm = state_machine
        self._recording_process = None

    def start(self) -> bool:
        """Start recording audio. Returns False if already recording."""
        if not self._sm.start_recording():
            return False

        self._recording_process = subprocess.Popen(
            ["sox", "-d", "-r", "16000", "-c", "1", RECORDING_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True

    def stop(self) -> bool:
        """Stop recording and transition to TRANSCRIBING. Returns False if not recording."""
        if self._recording_process and self._recording_process.poll() is None:
            self._recording_process.terminate()
            try:
                self._recording_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._recording_process.kill()

        self._recording_process = None
        return self._sm.stop_recording()

    def transcribe(
        self,
        audio_path: str,
        model: Optional[WhisperModel],
        language: str = "auto",
        beam_size: int = 1,
        best_of: int = 2,
    ) -> Optional[str]:
        """Transcribe an audio file. Returns None if transcription fails."""
        if model is None:
            print(
                "[audio] Model not loaded, skipping transcription",
                file=__import__("sys").stderr,
            )
            return None

        try:
            segments, _info = model.transcribe(
                audio_path,
                language=language,
                beam_size=beam_size,
                best_of=best_of,
            )
            text_parts = [seg.text.strip() for seg in segments]
            text = " ".join(text_parts)
            return text if text else None
        except Exception as exc:
            print(f"[audio] Transcription error: {exc}", file=__import__("sys").stderr)
            return None

    def cleanup_audio_file(self, audio_path: str = RECORDING_PATH) -> None:
        """Remove the temporary audio file after transcription."""
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except OSError:
            pass

    def play_sound(self, sound_name: str = "Pop.aiff") -> None:
        """Play a system sound."""
        subprocess.Popen(
            ["afplay", f"/System/Library/Sounds/{sound_name}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @property
    def is_recording(self) -> bool:
        return self._sm.is_recording

    @property
    def is_transcribing(self) -> bool:
        return self._sm.is_transcribing

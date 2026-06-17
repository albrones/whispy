"""Linux system-sound notifier (paplay / ffplay).

Plays short freedesktop cue sounds, preferring ``paplay`` (PulseAudio/PipeWire)
and falling back to ``ffplay``. If neither the player nor a sound file is
available the calls degrade to a silent no-op — sounds are a nicety, not a
requirement.
"""

import shutil
import subprocess

# Candidate freedesktop theme sounds, by purpose. The first that exists wins.
_RECORDING_START_SOUNDS = [
    "/usr/share/sounds/freedesktop/stereo/dialog-information.oga",
    "/usr/share/sounds/freedesktop/stereo/message.oga",
]
_SUCCESS_SOUNDS = [
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
]


def _first_existing(paths: list[str]) -> str | None:
    import os

    for p in paths:
        if os.path.exists(p):
            return p
    return None


class LinuxNotifier:
    """Plays short cue sounds via ``paplay``/``ffplay`` (fire-and-forget)."""

    def __init__(self) -> None:
        self._player = self._resolve_player()

    @staticmethod
    def _resolve_player() -> list[str] | None:
        if shutil.which("paplay"):
            return ["paplay"]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]
        return None

    def _play(self, candidates: list[str]) -> None:
        if not self._player:
            return
        sound = _first_existing(candidates)
        if not sound:
            return
        subprocess.Popen(
            [*self._player, sound],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def recording_started(self) -> None:
        self._play(_RECORDING_START_SOUNDS)

    def transcription_succeeded(self) -> None:
        self._play(_SUCCESS_SOUNDS)

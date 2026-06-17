"""macOS system-sound notifier (afplay)."""

import subprocess

_RECORDING_START_SOUND = "/System/Library/Sounds/Tink.aiff"
_SUCCESS_SOUND = "/System/Library/Sounds/Pop.aiff"


class MacNotifier:
    """Plays short cue sounds via ``afplay`` (fire-and-forget)."""

    def _play(self, path: str) -> None:
        subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def recording_started(self) -> None:
        self._play(_RECORDING_START_SOUND)

    def transcription_succeeded(self) -> None:
        self._play(_SUCCESS_SOUND)

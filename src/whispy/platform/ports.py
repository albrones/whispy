"""Platform port interfaces (structural ``typing.Protocol``).

The OS-coupled seams — hotkey listening, text injection, audio capture, the
tray/menu surface, and system sounds — are expressed here as structural
interfaces. The core engine depends only on these ports; concrete per-OS
adapters live under ``platform/macos`` and ``platform/linux`` and are bound at
runtime by ``platform.detect()``.

These are ``runtime_checkable`` so adapter conformance can be asserted in the
CI tier without a live OS seam.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class HotkeyListener(Protocol):
    """Global trigger-key listener.

    Constructed with the configured trigger and press/release callbacks; the
    engine starts and stops it over the daemon lifecycle.
    """

    active: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...


@runtime_checkable
class TextInjector(Protocol):
    """Injects transcribed text into the focused application."""

    def inject(self, text: str) -> None: ...

    def update_config(self, copy_to_clipboard: bool) -> None: ...


@runtime_checkable
class AudioRecorder(Protocol):
    """Captures audio to the recording path and transcribes it.

    Capture is cross-platform (``sounddevice``); the same recorder serves both
    macOS and Linux. Transcription stays here because the engine drives it
    through the same collaborator.
    """

    def start(self) -> bool: ...

    def stop(self) -> bool: ...

    def cleanup_audio_file(self, audio_path: str = ...) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """Plays the short system sounds that cue recording and completion."""

    def recording_started(self) -> None: ...

    def transcription_succeeded(self) -> None: ...


@runtime_checkable
class TrayUI(Protocol):
    """The status/menu surface (macOS rumps menu bar, Linux pystray tray).

    Built with the engine; it registers its own state callbacks and runs the
    platform UI loop. ``run`` blocks on the main thread for the daemon's life.
    """

    def run(self) -> None: ...


# Factory signatures used by ``platform.detect()``. Kept as type aliases for
# documentation; the detect layer returns these as plain callables.
MakeAudioRecorder = Callable[..., AudioRecorder]
MakeTextInjector = Callable[..., TextInjector]
MakeNotifier = Callable[[], Notifier]
MakeHotkeyListener = Callable[..., HotkeyListener]
MakeTray = Callable[..., TrayUI]

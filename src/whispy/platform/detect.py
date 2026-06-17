"""Runtime platform detection and adapter binding.

``detect()`` selects the adapter set for the current OS based on
``sys.platform`` and returns a :class:`PlatformAdapters` bundle of factories.
The factories import their concrete modules lazily (inside the closure) so that
selecting a platform never drags in another platform's optional dependencies
(``pynput``/``pystray`` on Linux, ``Quartz``/``rumps`` on macOS).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from .ports import (
    MakeAudioRecorder,
    MakeHotkeyListener,
    MakeNotifier,
    MakeTextInjector,
    MakeTray,
)

# Linux v1 push-to-talk default. ``pynput`` names the right Control key
# ``ctrl_r``; documented to users as "Right Ctrl".
LINUX_DEFAULT_TRIGGER = "ctrl_r"


@dataclass(frozen=True)
class PlatformAdapters:
    """Bound adapter set for one operating system.

    ``default_trigger`` is the trigger value used when config leaves it unset:
    the Fn keycode (63) on macOS, a documented push-to-talk key on Linux.
    """

    name: str
    default_trigger: Any
    make_audio_recorder: MakeAudioRecorder
    make_text_injector: MakeTextInjector
    make_notifier: MakeNotifier
    make_hotkey_listener: MakeHotkeyListener
    make_tray: MakeTray


def _macos_adapters() -> PlatformAdapters:
    from ..hardware.event_decode import DEFAULT_TRIGGER_KEYCODE

    def make_audio_recorder(state_machine):
        from ..core.audio import AudioEngine

        return AudioEngine(state_machine)

    def make_text_injector(copy_to_clipboard=False):
        from ..hardware.injection import TextInjector

        return TextInjector(copy_to_clipboard=copy_to_clipboard)

    def make_notifier():
        from .macos.notifier import MacNotifier

        return MacNotifier()

    def make_hotkey_listener(trigger, on_trigger_press, on_trigger_release):
        from ..hardware.event_tap import EventTapListener

        return EventTapListener(
            trigger_keycode=trigger,
            on_trigger_press=on_trigger_press,
            on_trigger_release=on_trigger_release,
        )

    def make_tray(engine):
        from ..ui.menu_bar import WhisperMenuBarApp

        return WhisperMenuBarApp(engine)

    return PlatformAdapters(
        name="macos",
        default_trigger=DEFAULT_TRIGGER_KEYCODE,
        make_audio_recorder=make_audio_recorder,
        make_text_injector=make_text_injector,
        make_notifier=make_notifier,
        make_hotkey_listener=make_hotkey_listener,
        make_tray=make_tray,
    )


def _linux_adapters() -> PlatformAdapters:
    def make_audio_recorder(state_machine):
        from ..core.audio import AudioEngine

        return AudioEngine(state_machine)

    def make_text_injector(copy_to_clipboard=False):
        from .linux.injection import XdotoolInjector

        return XdotoolInjector(copy_to_clipboard=copy_to_clipboard)

    def make_notifier():
        from .linux.notifier import LinuxNotifier

        return LinuxNotifier()

    def make_hotkey_listener(trigger, on_trigger_press, on_trigger_release):
        from .linux.hotkey import PynputHotkeyListener

        return PynputHotkeyListener(
            trigger_key=trigger,
            on_trigger_press=on_trigger_press,
            on_trigger_release=on_trigger_release,
        )

    def make_tray(engine):
        from .linux.tray import PystrayApp

        return PystrayApp(engine)

    return PlatformAdapters(
        name="linux",
        default_trigger=LINUX_DEFAULT_TRIGGER,
        make_audio_recorder=make_audio_recorder,
        make_text_injector=make_text_injector,
        make_notifier=make_notifier,
        make_hotkey_listener=make_hotkey_listener,
        make_tray=make_tray,
    )


def detect(platform: str | None = None) -> PlatformAdapters:
    """Return the adapter set for ``platform`` (defaults to ``sys.platform``).

    Raises ``NotImplementedError`` naming the platform and the supported set on
    an OS with no adapters (e.g. ``win32`` in v1) rather than returning a
    partial binding.
    """
    plat = platform if platform is not None else sys.platform
    if plat == "darwin":
        return _macos_adapters()
    if plat.startswith("linux"):
        return _linux_adapters()
    raise NotImplementedError(
        f"Whispy supports macOS ('darwin') and Linux ('linux') in v1; "
        f"got sys.platform={plat!r}. No adapter set is available for this platform."
    )

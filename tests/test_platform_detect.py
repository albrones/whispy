"""Unit tests for the platform factory and macOS port conformance.

CI tier: ``sys.platform`` is selected explicitly via ``detect(platform=...)`` so
no live OS seam is required.
"""

import sys
from pathlib import Path

import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.platform.detect import LINUX_DEFAULT_TRIGGER, detect
from whispy.platform.ports import (
    AudioRecorder,
    Notifier,
    TextInjector,
)


class TestFactorySelection:
    def test_darwin_selects_macos_adapters(self):
        adapters = detect("darwin")
        assert adapters.name == "macos"
        assert adapters.default_trigger == 63

    def test_linux_selects_linux_adapters(self):
        adapters = detect("linux")
        assert adapters.name == "linux"
        assert adapters.default_trigger == LINUX_DEFAULT_TRIGGER

    def test_linux_variant_string_selects_linux(self):
        # sys.platform can be "linux" or "linux2"; both must resolve to Linux.
        assert detect("linux2").name == "linux"

    def test_unsupported_platform_raises_actionable_error(self):
        with pytest.raises(NotImplementedError) as exc:
            detect("win32")
        msg = str(exc.value)
        assert "win32" in msg
        assert "darwin" in msg and "linux" in msg


class TestMacAdapterConformance:
    """The macOS adapters satisfy the structural ports (runtime_checkable)."""

    def test_audio_recorder_conforms(self):
        from whispy.core.state_machine import StateMachine

        adapters = detect("darwin")
        recorder = adapters.make_audio_recorder(StateMachine())
        assert isinstance(recorder, AudioRecorder)

    def test_text_injector_conforms(self):
        adapters = detect("darwin")
        injector = adapters.make_text_injector(copy_to_clipboard=False)
        assert isinstance(injector, TextInjector)

    def test_notifier_conforms(self):
        adapters = detect("darwin")
        notifier = adapters.make_notifier()
        assert isinstance(notifier, Notifier)


class TestLinuxAdapterConformance:
    """Linux injector/notifier conform without needing pynput/pystray."""

    def test_text_injector_conforms(self):
        adapters = detect("linux")
        injector = adapters.make_text_injector(copy_to_clipboard=False)
        assert isinstance(injector, TextInjector)

    def test_notifier_conforms(self):
        adapters = detect("linux")
        notifier = adapters.make_notifier()
        assert isinstance(notifier, Notifier)

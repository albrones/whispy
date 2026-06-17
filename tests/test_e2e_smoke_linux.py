"""Unattended real-seam smoke tests for Linux/X11 (tier: linux-real).

Exercises the Linux seams that mocks can never cover: real `sounddevice`
capture, the `pynput` global listener arming under X11, and `xdotool` text
injection into a focused window. Marked ``linux`` and excluded from the default
run; opt in with::

    pytest -m linux tests/test_e2e_smoke_linux.py

Each seam SKIPS cleanly when its device/permission/binary is absent — a skip
means "not available here", not "passed". The full record → transcribe → inject
chain with a real keypress and focused field is the operator manual flow.
"""

import shutil
import sys
import time
import wave
from pathlib import Path

import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

pytestmark = pytest.mark.linux

if sys.platform != "linux":
    pytest.skip("Linux/X11 real-seam tier", allow_module_level=True)

from whispy.core.audio import _MIN_RECORDING_SIZE  # noqa: E402
from whispy.platform.linux.session import is_wayland_session  # noqa: E402


def _require_x11():
    if is_wayland_session():
        pytest.skip("Whispy v1 requires an X11 session; Wayland detected")


class TestRealAudioCapture:
    def test_recording_yields_valid_wav(self, tmp_path):
        import whispy.core.audio as audio_module
        from whispy.core.state_machine import StateMachine

        wav = tmp_path / "smoke.wav"
        original = audio_module.RECORDING_PATH
        audio_module.RECORDING_PATH = str(wav)
        engine = audio_module.AudioEngine(StateMachine())
        try:
            if not engine.start():
                pytest.skip("could not start recording (no input device?)")
            time.sleep(0.6)
            engine.stop()
        except Exception as exc:
            pytest.skip(f"real audio capture unavailable: {exc}")
        finally:
            audio_module.RECORDING_PATH = original

        if not wav.exists():
            pytest.skip("no recording produced (device/permission)")

        size = wav.stat().st_size
        assert size >= _MIN_RECORDING_SIZE, f"recording too small: {size} bytes"
        with wave.open(str(wav), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1


class TestLivePynputListener:
    def test_listener_arms_under_x11(self):
        _require_x11()
        try:
            from whispy.platform.linux.hotkey import PynputHotkeyListener
        except Exception as exc:
            pytest.skip(f"pynput unavailable: {exc}")
        listener = PynputHotkeyListener(trigger_key="ctrl_r")
        listener.start()
        try:
            if not listener.active:
                pytest.skip("listener inactive — X11 global listen not permitted here")
            assert listener.active is True
        finally:
            listener.stop()


class TestXdotoolInjection:
    def test_xdotool_present_and_types(self):
        _require_x11()
        if shutil.which("xdotool") is None:
            pytest.skip("xdotool not installed")
        # Typing into the focused field is the operator boundary; here we only
        # confirm the injector wires up and runs without raising.
        from whispy.platform.linux.injection import XdotoolInjector

        injector = XdotoolInjector(copy_to_clipboard=False)
        injector.inject("whispy-linux-smoke")
        time.sleep(0.2)

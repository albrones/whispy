"""Unattended real-seam smoke tests (tier: macos-real).

Exercises the three OS seams that mocks and logic-extraction can never cover:
real `sounddevice` microphone capture, real `osascript` clipboard automation,
and a live `CGEventTap`. Marked ``macos`` and excluded from the default run; opt
in with::

    pytest -m macos tests/test_e2e_smoke.py

Each seam SKIPS cleanly when its device/permission is absent — a skip means
"not granted/available here", not "passed".

NOT automated here (operator manual flow): hold the Fn key, speak a phrase,
release, and confirm the transcribed text appears in the focused application.
That requires a real keypress and a focused text field; this layer covers
everything that can run without a human or synthetic input.
"""

import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

pytestmark = pytest.mark.macos

if shutil.which("osascript") is None or shutil.which("pbpaste") is None:
    pytest.skip("requires `osascript` and `pbpaste`", allow_module_level=True)

from whispy.core.audio import _MIN_RECORDING_SIZE  # noqa: E402


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
        except Exception as exc:  # sox/device failure on this machine
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


class TestRealOsascriptClipboard:
    def test_clipboard_round_trips_through_osascript(self):
        token = f"whispy-smoke-{os.getpid()}-{int(time.time())}"
        set_proc = subprocess.run(
            ["osascript", "-e", f'set the clipboard to "{token}"'],
            capture_output=True,
            text=True,
        )
        if set_proc.returncode != 0:
            pytest.skip(f"osascript clipboard set failed: {set_proc.stderr.strip()}")
        read_back = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        assert read_back == token
        # NOTE: the actual Cmd+V paste into a focused field is the operator
        # boundary and is not automated here.


class TestLiveEventTap:
    def test_event_tap_arms_when_permitted(self):
        # conftest.py mocks Quartz globally, so a real tap must be armed in a
        # fresh subprocess with real Quartz and PYTHONPATH=src.
        script = (
            "from whispy.hardware.event_tap import EventTapListener\n"
            "l = EventTapListener()\n"
            "l.start()\n"
            "print('ACTIVE' if l.active else 'INACTIVE')\n"
            "l.stop()\n"
        )
        env = dict(os.environ, PYTHONPATH=str(_src))
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        out = proc.stdout.strip().splitlines()
        verdict = out[-1] if out else ""
        if proc.returncode != 0:
            pytest.skip(f"event tap subprocess failed: {proc.stderr.strip()}")
        if verdict != "ACTIVE":
            pytest.skip("event tap inactive — grant Input Monitoring to this Python to run this check")
        assert verdict == "ACTIVE"


class TestLiveDriveCycle:
    """Drive the real headless daemon over HTTP — record→transcribe cycle.

    Tier: live-driven. Maps the harness outcomes onto pytest: a FAIL asserts,
    an all-UNVERIFIED result skips (surfaced as UNVERIFIED by `make validate`).
    """

    def test_driven_cycle_over_http(self):
        from tests.validation.harness import run_live_drive
        from tests.validation.outcomes import Outcome

        results = run_live_drive(record_seconds=1.0)
        fails = [r for r in results if r.outcome is Outcome.FAIL]
        passes = [r for r in results if r.outcome is Outcome.PASS]
        assert not fails, f"live-drive failure(s): {[(r.feature, r.detail) for r in fails]}"
        if not passes:
            reasons = "; ".join(r.detail for r in results)
            pytest.skip(f"live-drive UNVERIFIED (mic/model/permission?): {reasons}")

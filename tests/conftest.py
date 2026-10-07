"""Shared fixtures for Whispy tests.

Mocks macOS-only dependencies (Quartz, rumps) so tests can run on any platform.
Provides shared fixtures for Engine, DictationState, and temporary directories.
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Longer than the injector's clipboard-restore delay, so one quiet interval
# proves the worker has no further step pending rather than merely sleeping.
_WORKER_QUIET_S = 0.25

# Mock macOS-only dependencies before any whispy imports
if "Quartz" not in sys.modules:
    sys.modules["Quartz"] = MagicMock()
if "rumps" not in sys.modules:
    sys.modules["rumps"] = MagicMock()

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_src = Path(__file__).parent.parent / "src"
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
# Also remove '' (current directory) if it points to the project root
if "" in sys.path and str(Path(".").resolve()) == Path(_project_root).resolve():
    sys.path.remove("")
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


@pytest.fixture(autouse=True)
def isolated_home(request, tmp_path_factory, monkeypatch):
    """Point HOME at a throwaway directory for the default test tier.

    An ``Engine()`` built without ``config_path`` reads and *saves*
    ``~/.config/whispy/config.json``. Without this, every test run rewrote the
    developer's real config — ``streaming_enabled: false`` included, which
    silently turned Type while speaking off on the installed app. The real-seam
    tiers keep the real HOME: they need the model cache under it.
    """
    if request.node.get_closest_marker("macos") or request.node.get_closest_marker("linux"):
        return
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture(autouse=True)
def fake_audio_capture(request):
    """Replace the sounddevice backend with a fake for the default test tier.

    The real PortAudio device is only used by the per-OS real-seam tiers
    (`macos`/`linux` markers). Everywhere else, the fake stream synchronously
    delivers ~1 second of int16 silence to the capture callback on ``start()``
    so readiness resolves instantly (no device, no 2s timeout) and the WAV at
    RECORDING_PATH is well-formed.
    """
    if request.node.get_closest_marker("macos") or request.node.get_closest_marker("linux"):
        yield
        return

    import whispy.core.audio as audio_module

    class _FakeStream:
        def __init__(self, samplerate, channels, dtype, callback, **_kw):
            self._sr = samplerate
            self._ch = channels
            self._cb = callback

        def start(self):
            frames = self._sr  # ~1 second
            data = bytes(frames * self._ch * audio_module.SAMPLE_WIDTH)
            if self._cb:
                self._cb(data, frames, None, None)

        def stop(self):
            pass

        def close(self):
            pass

    fake_sd = MagicMock()
    fake_sd.RawInputStream = _FakeStream
    original = audio_module.sd
    audio_module.sd = fake_sd
    try:
        yield
    finally:
        audio_module.sd = original


@pytest.fixture
def tmp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="whispy_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def config_path(tmp_dir):
    """Create a temporary config directory and return the config file path."""
    config_dir = tmp_dir / ".config" / "whispy"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


@pytest.fixture
def state():
    """Create a fresh DictationState instance."""
    from whispy.core.engine import DictationState

    return DictationState()


@pytest.fixture
def engine(state, config_path, tmp_dir):
    """Create a fresh Engine instance with a DictationState."""
    import whispy.core.audio as audio_module
    from whispy.core.engine import Engine

    # Patch RECORDING_PATH before Engine/AudioEngine init so the audio engine
    # uses a temp path instead of /tmp/whispy.wav
    recording_file = tmp_dir / "whispy.wav"
    recording_file.write_bytes(b"\x00" * 6000)
    original_path = audio_module.RECORDING_PATH
    audio_module.RECORDING_PATH = str(recording_file)

    eng = Engine(state, config_path)

    audio_module.RECORDING_PATH = original_path

    return eng


@pytest.fixture
def sm():
    """Create a fresh StateMachine instance."""
    from whispy.core.state_machine import StateMachine

    return StateMachine()


@pytest.fixture
def temp_audio_file(tmp_dir):
    """Create a temporary audio file path and return it."""
    audio_path = tmp_dir / "test_audio.wav"
    audio_path.write_bytes(b"\x00" * 100)
    return str(audio_path)


@pytest.fixture
def mock_asr_model(mocker):
    """Create a mock Parakeet model.

    The backend contract is one method: ``recognize(audio)`` returns a string
    (empty for silence). No spec= here — onnx_asr builds the model class at
    load time, so there is no importable type to spec against.
    """
    mock = MagicMock()
    mock.recognize.return_value = ""
    return mock


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run and subprocess.Popen.

    Teardown waits for the injector's worker thread to go quiet before the
    patches come off. ``TextInjector`` runs its steps on a daemon thread and
    sleeps ``_CLIPBOARD_RESTORE_DELAY`` before the clipboard-restore step, so a
    test that returns without draining the full sequence leaves a ``Popen``
    pending. That call lands either in the *next* test's mock -- shifting every
    index in ``call_args_list`` and failing assertions in a test that did
    nothing wrong -- or, once unpatched, on the real pasteboard.
    """
    run_mock = mocker.patch("subprocess.run")
    popen_mock = mocker.patch("subprocess.Popen")
    popen_instance = MagicMock()
    popen_mock.return_value = popen_instance
    popen_instance.poll.return_value = None

    yield run_mock, popen_mock, popen_instance

    # Only tests that actually spawned something can have work in flight, so
    # the common case costs nothing.
    if not popen_mock.call_count:
        return
    deadline = time.monotonic() + 2.0
    seen = -1
    while popen_mock.call_count != seen and time.monotonic() < deadline:
        seen = popen_mock.call_count
        time.sleep(_WORKER_QUIET_S)


@pytest.fixture(scope="session")
def asr_model():
    """Load the real Parakeet model once per session (int8, CPU).

    Session-scoped and shared here rather than per-module so the two real-model
    tiers — the macOS-only semantic tests and the platform-neutral non-speech
    tests — load the 639 MB model once between them instead of once each.
    Nothing outside those tiers requests it, so the default run never loads it.
    """
    from whispy.core.engine import _load_model

    return _load_model({})


@pytest.fixture
def real_audio_engine():
    """AudioEngine wired to a real StateMachine, for the real `transcribe` path."""
    from whispy.core.audio import AudioEngine
    from whispy.core.state_machine import StateMachine

    return AudioEngine(StateMachine())

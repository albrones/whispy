"""Shared fixtures for Whispy tests.

Mocks macOS-only dependencies (Quartz, rumps) so tests can run on any platform.
Provides shared fixtures for Engine, DictationState, and temporary directories.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


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
def engine(state, config_path):
    """Create a fresh Engine instance with a DictationState."""
    from whispy.core.engine import Engine

    return Engine(state, config_path)


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
def mock_whisper_model(mocker):
    """Create a mock WhisperModel."""
    from faster_whisper import WhisperModel

    mock = MagicMock(spec=WhisperModel)
    mock.transcribe.return_value = iter([])
    return mock


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run and subprocess.Popen."""
    run_mock = mocker.patch("subprocess.run")
    popen_mock = mocker.patch("subprocess.Popen")
    popen_instance = MagicMock()
    popen_mock.return_value = popen_instance
    return run_mock, popen_mock, popen_instance

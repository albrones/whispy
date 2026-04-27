"""Fixtures for HTTP API tests."""

import sys
from pathlib import Path

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_src = Path(__file__).parent.parent.parent / "src"
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
# Also remove '' (current directory) if it points to the project root
if "" in sys.path and str(Path(".").resolve()) == Path(_project_root).resolve():
    sys.path.remove("")
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import pytest

from whispy.core.engine import DictationState, Engine


@pytest.fixture
def mock_engine(mocker):
    """Create a mock Engine with common return values."""
    ds = DictationState()
    engine = Engine(ds)

    mocker.patch.object(
        engine,
        "get_status",
        return_value={
            "is_recording": False,
            "is_transcribing": False,
            "fn_listener_active": False,
            "model_loaded": False,
            "model_loading": False,
            "fsm": {
                "state": "IDLE",
                "is_idle": True,
                "is_recording": False,
                "is_transcribing": False,
            },
        },
    )

    return engine

"""Tests for menu-bar settings callbacks.

Focus: selecting a model in the menu must both persist the choice and apply it
live (reload the model), mirroring the HTTP /config path. The callbacks are
exercised as unbound methods against a lightweight fake ``self`` so the test
never constructs the real rumps.App / AppKit run loop.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# rumps is macOS-only and conftest installs a bare MagicMock for it — but a
# MagicMock can't serve as a real base class, so `class App(rumps.App)` collapses
# the whole class into a Mock and its methods become unreachable. Install a
# lightweight stub whose `App` is a REAL class, then (re)import the module so the
# class is built against it.
_fake_rumps = types.ModuleType("rumps")


class _App:  # real, subclassable base
    def __init__(self, *args, **kwargs):
        pass


_fake_rumps.App = _App
_fake_rumps.MenuItem = MagicMock
_fake_rumps.Timer = MagicMock
_fake_rumps.notification = MagicMock()
_fake_rumps.quit_application = MagicMock()
sys.modules["rumps"] = _fake_rumps
# Drop any cached copy built against the conftest MagicMock so the import below
# rebuilds the class against the real _App base.
sys.modules.pop("whispy.ui.menu_bar", None)

from whispy.ui.menu_bar import WhisperMenuBarApp


def _fake_app(current_model="small", needs_reload=True):
    """A minimal stand-in exposing only what _on_model_select touches."""
    engine = MagicMock()
    engine.state.config = {"model_size": current_model}
    engine.update_config.return_value = needs_reload
    return SimpleNamespace(
        engine=engine,
        _model_items={"small": MagicMock(), "base": MagicMock()},
        _update_model_title=MagicMock(),
    )


class TestModelSelectAppliesLive:
    def test_changing_model_persists_and_reloads(self, mocker):
        reload_mock = mocker.patch("whispy.core.engine.load_model_async")
        app = _fake_app(current_model="small", needs_reload=True)
        sender = SimpleNamespace(_model_key="base")

        WhisperMenuBarApp._on_model_select(app, sender)

        # Persisted via update_config...
        app.engine.update_config.assert_called_once_with({"model_size": "base"})
        # ...and applied live by reloading the model.
        reload_mock.assert_called_once_with(app.engine)

    def test_no_reload_when_update_reports_no_change(self, mocker):
        reload_mock = mocker.patch("whispy.core.engine.load_model_async")
        app = _fake_app(current_model="small", needs_reload=False)
        sender = SimpleNamespace(_model_key="base")

        WhisperMenuBarApp._on_model_select(app, sender)

        app.engine.update_config.assert_called_once()
        reload_mock.assert_not_called()

    def test_selecting_current_model_is_noop(self, mocker):
        reload_mock = mocker.patch("whispy.core.engine.load_model_async")
        app = _fake_app(current_model="base")
        sender = SimpleNamespace(_model_key="base")

        WhisperMenuBarApp._on_model_select(app, sender)

        app.engine.update_config.assert_not_called()
        reload_mock.assert_not_called()

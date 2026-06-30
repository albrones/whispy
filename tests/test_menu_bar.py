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

from whispy.ui import menu_theme
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


class TestCheckmarkInvariant:
    """Selecting an item must leave exactly one accent checkmark in the group."""

    def _item(self, label):
        # _menuitem=None forces apply_title's plain-string path (sets .title).
        return SimpleNamespace(_label=label, _menuitem=None, title=label)

    def test_single_check_after_model_select(self, mocker, monkeypatch):
        # Force menu_theme into plain-string mode so titles are inspectable.
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        mocker.patch("whispy.core.engine.load_model_async")

        items = {"small": self._item("Small"), "base": self._item("Base")}
        engine = MagicMock()
        engine.state.config = {"model_size": "small"}
        engine.update_config.return_value = False
        app = SimpleNamespace(engine=engine, _model_items=items, _update_model_title=MagicMock())

        WhisperMenuBarApp._on_model_select(app, SimpleNamespace(_model_key="base"))

        checked = [k for k, it in items.items() if it.title.startswith(menu_theme.CHECK)]
        assert checked == ["base"]


class TestLoginItemToggle:
    """_on_toggle_login_item persists the setting in config and syncs the OS."""

    def _sender(self, label="Start at login"):
        # _menuitem=None forces apply_title's plain-string path (sets .title).
        return SimpleNamespace(_label=label, _menuitem=None, title=label)

    def _app(self, current):
        engine = MagicMock()
        engine.state.config = {"start_at_login": current}
        return SimpleNamespace(engine=engine)

    def test_off_then_persists_true_enables_and_titles_on(self, mocker, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        import whispy.ui.menu_bar as mb

        li = mocker.patch.object(mb, "login_item")
        app = self._app(current=False)
        sender = self._sender()

        WhisperMenuBarApp._on_toggle_login_item(app, sender)

        app.engine.update_config.assert_called_once_with({"start_at_login": True})
        li.enable.assert_called_once_with()
        li.disable.assert_not_called()
        assert sender.title.rstrip().endswith(menu_theme.CHECK)

    def test_on_then_persists_false_disables_and_titles_off(self, mocker, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        import whispy.ui.menu_bar as mb

        li = mocker.patch.object(mb, "login_item")
        app = self._app(current=True)
        sender = self._sender()

        WhisperMenuBarApp._on_toggle_login_item(app, sender)

        app.engine.update_config.assert_called_once_with({"start_at_login": False})
        li.disable.assert_called_once_with()
        li.enable.assert_not_called()
        assert not sender.title.rstrip().endswith(menu_theme.CHECK)


class TestLoginItemReconcile:
    """_reconcile_login_item syncs OS registration to the saved setting."""

    def test_enables_when_wanted_but_os_off(self, mocker):
        import whispy.ui.menu_bar as mb

        li = mocker.patch.object(mb, "login_item")
        li.is_enabled.return_value = False
        WhisperMenuBarApp._reconcile_login_item(True)
        li.enable.assert_called_once_with()
        li.disable.assert_not_called()

    def test_disables_when_not_wanted_but_os_on(self, mocker):
        import whispy.ui.menu_bar as mb

        li = mocker.patch.object(mb, "login_item")
        li.is_enabled.return_value = True
        WhisperMenuBarApp._reconcile_login_item(False)
        li.disable.assert_called_once_with()
        li.enable.assert_not_called()

    def test_noop_when_already_in_sync(self, mocker):
        import whispy.ui.menu_bar as mb

        li = mocker.patch.object(mb, "login_item")
        li.is_enabled.return_value = True
        WhisperMenuBarApp._reconcile_login_item(True)
        li.enable.assert_not_called()
        li.disable.assert_not_called()


class TestLoginItemUnwrap:
    """register/unregister return a bare bool under raw loadBundle (no
    BridgeSupport), or an (ok, error) tuple with metadata. _unwrap handles both."""

    def test_bare_bool(self):
        from whispy.platform.macos.login_item import _unwrap

        assert _unwrap(True) == (True, None)
        assert _unwrap(False) == (False, None)

    def test_tuple(self):
        from whispy.platform.macos.login_item import _unwrap

        assert _unwrap((True, None)) == (True, None)
        ok, err = _unwrap((False, "boom"))
        assert ok is False and err == "boom"


class TestRestartHandoff:
    """_on_reload hands the :9090 lock to the replacement without a parallel
    instance: a detached port-free waiter relaunches, and we never force-new."""

    def test_bundle_restart_uses_waiter_and_no_force_new(self, mocker):
        import whispy.ui.menu_bar as mb

        mocker.patch.object(mb, "resolve_app_bundle", return_value="/Apps/Whispy.app")
        popen = mocker.patch.object(mb.subprocess, "Popen")
        quit_app = mocker.patch.object(mb.rumps, "quit_application")

        WhisperMenuBarApp._on_reload(SimpleNamespace(), None)

        popen.assert_called_once()
        argv = popen.call_args[0][0]
        assert argv[0] == sys.executable and argv[1] == "-c"
        assert argv[2] == mb._RELAUNCH_WAITER  # detached port-free waiter
        assert "/usr/bin/open" in argv and "/Apps/Whispy.app" in argv
        assert "-n" not in argv  # must NOT force a parallel instance
        quit_app.assert_called_once()

    def test_source_restart_reexecs_script_via_waiter(self, mocker):
        import whispy.ui.menu_bar as mb

        mocker.patch.object(mb, "resolve_app_bundle", return_value=None)
        mocker.patch.object(mb, "resolve_daemon_script", return_value="/src/whispy_daemon.py")
        mocker.patch.object(mb, "daemon_script_exists", return_value=True)
        popen = mocker.patch.object(mb.subprocess, "Popen")
        quit_app = mocker.patch.object(mb.rumps, "quit_application")

        WhisperMenuBarApp._on_reload(SimpleNamespace(), None)

        argv = popen.call_args[0][0]
        assert argv[:3] == [sys.executable, "-c", mb._RELAUNCH_WAITER]
        assert "/src/whispy_daemon.py" in argv
        quit_app.assert_called_once()


class TestStatusDisplayMarshaling:
    """update_status_display must hop to the main thread before touching AppKit."""

    def test_off_main_thread_defers_to_callafter(self, mocker):
        import whispy.ui.menu_bar as mb

        mocker.patch.object(mb, "NSThread").isMainThread.return_value = False
        app_helper = mocker.patch.object(mb, "AppHelper")
        app = SimpleNamespace(_update_status_on_main=MagicMock())

        WhisperMenuBarApp.update_status_display(app)

        # Deferred to the main run loop — not run inline on this thread.
        app_helper.callAfter.assert_called_once_with(app._update_status_on_main)
        app._update_status_on_main.assert_not_called()

    def test_on_main_thread_runs_inline(self, mocker):
        import whispy.ui.menu_bar as mb

        mocker.patch.object(mb, "NSThread").isMainThread.return_value = True
        app_helper = mocker.patch.object(mb, "AppHelper")
        app = SimpleNamespace(_update_status_on_main=MagicMock())

        WhisperMenuBarApp.update_status_display(app)

        app._update_status_on_main.assert_called_once_with()
        app_helper.callAfter.assert_not_called()


"""Tests for menu-bar settings callbacks.

Focus: selecting a setting in the menu must both persist the choice and apply
it live, mirroring the HTTP /config path. The callbacks are exercised as
unbound methods against a lightweight fake ``self`` so the test never
constructs the real rumps.App / AppKit run loop.

The Model and Language submenus are gone with the Whisper backend — Parakeet
ships in one size and detects language itself — so Trigger is the remaining
selection group.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# The module under test pulls in AppKit (pyobjc) transitively via menu_theme,
# which does not exist off macOS. Skip the whole module at collection time on
# other platforms (the Linux CI tier collects it too).
if sys.platform != "darwin":
    pytest.skip("menu bar is macOS-only (AppKit)", allow_module_level=True)

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


def _fake_trigger_app(current_trigger=None, items=None, persist=False):
    """A minimal stand-in exposing only what _on_trigger_select touches.

    ``persist=True`` makes update_config actually mutate the config, as the real
    one does, so the checkmark invariant is checked against the post-update
    state instead of the stale one.
    """
    engine = MagicMock()
    engine.state.config = {"trigger": current_trigger}
    if persist:
        engine.update_config.side_effect = engine.state.config.update
    app = SimpleNamespace(
        engine=engine,
        _trigger_items=items if items is not None else [],
        _update_trigger_title=MagicMock(),
    )
    app._trigger_is_active = lambda value: value == engine.state.config["trigger"]
    return app


class TestNoModelOrLanguageMenu:
    """Neither submenu may come back: nothing in the config would receive it."""

    def test_model_select_callback_is_gone(self):
        assert not hasattr(WhisperMenuBarApp, "_on_model_select")

    def test_language_select_callback_is_gone(self):
        assert not hasattr(WhisperMenuBarApp, "_on_language_select")


class TestTriggerSelectAppliesLive:
    def test_changing_trigger_persists(self):
        app = _fake_trigger_app(current_trigger=None)
        WhisperMenuBarApp._on_trigger_select(app, SimpleNamespace(_trigger_value=54))

        app.engine.update_config.assert_called_once_with({"trigger": 54})
        app._update_trigger_title.assert_called_once()

    def test_selecting_current_trigger_is_noop(self):
        app = _fake_trigger_app(current_trigger=54)
        WhisperMenuBarApp._on_trigger_select(app, SimpleNamespace(_trigger_value=54))

        app.engine.update_config.assert_not_called()
        app._update_trigger_title.assert_not_called()


class TestCheckmarkInvariant:
    """Selecting an item must leave exactly one accent checkmark in the group."""

    def _item(self, label):
        # _menuitem=None forces apply_title's plain-string path (sets .title).
        return SimpleNamespace(_label=label, _menuitem=None, title=label)

    def _trigger_item(self, label, value):
        item = self._item(label)
        item._trigger_value = value
        return item

    def test_single_check_after_trigger_select(self, monkeypatch):
        # Force menu_theme into plain-string mode so titles are inspectable.
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)

        items = [self._trigger_item("Fn", None), self._trigger_item("Right Command", 54)]
        app = _fake_trigger_app(current_trigger=None, items=items, persist=True)

        WhisperMenuBarApp._on_trigger_select(app, SimpleNamespace(_trigger_value=54))

        checked = [it._label for it in items if it.title.startswith(menu_theme.CHECK)]
        assert checked == ["Right Command"]


class TestTriggerSelectCombinationPreset:
    """String-valued combination presets (added alongside the int keycodes)
    must persist, move the checkmark, and re-label the submenu title."""

    def _item(self, label, value):
        # _menuitem=None forces apply_title's plain-string path (sets .title).
        return SimpleNamespace(_label=label, _trigger_value=value, _menuitem=None, title=label)

    def test_selecting_combination_persists_checks_and_labels(self, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)

        items = [self._item("Fn", None), self._item("⌃⌥⌘E", "ctrl+alt+cmd+e")]
        engine = MagicMock()
        engine.state.config = {"trigger": None}
        engine.update_config.side_effect = engine.state.config.update
        app = SimpleNamespace(engine=engine, _trigger_items=items, trigger_menu=SimpleNamespace(title="Trigger: Fn"))
        app._trigger_is_active = lambda value: WhisperMenuBarApp._trigger_is_active(app, value)
        app._trigger_label = lambda: WhisperMenuBarApp._trigger_label(app)
        app._update_trigger_title = lambda: WhisperMenuBarApp._update_trigger_title(app)

        WhisperMenuBarApp._on_trigger_select(app, SimpleNamespace(_trigger_value="ctrl+alt+cmd+e"))

        engine.update_config.assert_called_once_with({"trigger": "ctrl+alt+cmd+e"})
        checked = [it._label for it in items if it.title.startswith(menu_theme.CHECK)]
        assert checked == ["⌃⌥⌘E"]
        assert app.trigger_menu.title == "Trigger: ⌃⌥⌘E"


class TestTriggerLabelRawString:
    """A configured string trigger matching no preset must render as itself,
    not be passed through keycode_to_name (which expects an int)."""

    def test_unmatched_combination_returns_raw_string(self):
        engine = MagicMock()
        engine.state.config = {"trigger": "ctrl+shift+z"}
        app = SimpleNamespace(engine=engine)
        app._trigger_is_active = lambda value: WhisperMenuBarApp._trigger_is_active(app, value)

        assert WhisperMenuBarApp._trigger_label(app) == "ctrl+shift+z"


class TestToggleTriggerMode:
    """_on_toggle_trigger_mode flips trigger_mode and persists it, mirroring
    _on_toggle_copy."""

    def _sender(self, label="Toggle mode"):
        # _menuitem=None forces apply_title's plain-string path (sets .title).
        return SimpleNamespace(_label=label, _menuitem=None, title=label)

    def _app(self, current):
        engine = MagicMock()
        engine.state.config = {"trigger_mode": current}
        return SimpleNamespace(engine=engine)

    def test_hold_to_toggle_persists_and_checks(self, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        app = self._app(current="hold")
        sender = self._sender()

        WhisperMenuBarApp._on_toggle_trigger_mode(app, sender)

        app.engine.update_config.assert_called_once_with({"trigger_mode": "toggle"})
        assert sender.title.rstrip().endswith(menu_theme.CHECK)

    def test_toggle_to_hold_persists_and_unchecks(self, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        app = self._app(current="toggle")
        sender = self._sender()

        WhisperMenuBarApp._on_toggle_trigger_mode(app, sender)

        app.engine.update_config.assert_called_once_with({"trigger_mode": "hold"})
        assert not sender.title.rstrip().endswith(menu_theme.CHECK)


class TestRefreshAccentsToggleMode:
    """_refresh_accents must rebuild the Toggle mode title from current config,
    same as it does for the clipboard toggle."""

    def test_rebuilds_toggle_mode_title_checked(self, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        engine = MagicMock()
        engine.state.config = {"trigger_mode": "toggle", "copy_to_clipboard": False}
        app = SimpleNamespace(
            engine=engine,
            _settings_header=SimpleNamespace(_menuitem=None, title=""),
            copy_menu=SimpleNamespace(_label="Copy to clipboard", _menuitem=None, title=""),
            toggle_mode_menu=SimpleNamespace(_label="Toggle mode", _menuitem=None, title=""),
            _trigger_items=[],
            update_status_display=MagicMock(),
        )

        WhisperMenuBarApp._refresh_accents(app)

        assert app.toggle_mode_menu.title.rstrip().endswith(menu_theme.CHECK)

    def test_rebuilds_toggle_mode_title_unchecked(self, monkeypatch):
        monkeypatch.setattr(menu_theme, "_appkit", lambda: None)
        engine = MagicMock()
        engine.state.config = {"trigger_mode": "hold", "copy_to_clipboard": False}
        app = SimpleNamespace(
            engine=engine,
            _settings_header=SimpleNamespace(_menuitem=None, title=""),
            copy_menu=SimpleNamespace(_label="Copy to clipboard", _menuitem=None, title=""),
            toggle_mode_menu=SimpleNamespace(_label="Toggle mode", _menuitem=None, title=""),
            _trigger_items=[],
            update_status_display=MagicMock(),
        )

        WhisperMenuBarApp._refresh_accents(app)

        assert not app.toggle_mode_menu.title.rstrip().endswith(menu_theme.CHECK)


class TestRecordingLimitAlert:
    """The recording-limit callback (engine, background thread) must queue a
    pending alert like the other engine-driven warnings."""

    def test_queues_alert_with_engine_message(self):
        app = SimpleNamespace(_pending_alerts=[])

        WhisperMenuBarApp._on_recording_limit_reached(app, "Recording stopped after 5 minutes.")

        [(subtitle, message, url)] = app._pending_alerts
        assert subtitle == "Dictation stopped"
        assert message == "Recording stopped after 5 minutes."
        assert url is None


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


class TestAlertWiring:
    """Blocker fix: model-load failure and missing permissions must reach the
    UI. The engine hooks exist; the bug class is a never-registered callback,
    so assert __init__ actually registers them."""

    def test_init_registers_alert_callbacks(self):
        import inspect

        src = inspect.getsource(WhisperMenuBarApp.__init__)
        assert "on_model_load_failed" in src
        assert "on_permission_missing" in src
        assert "on_injection_permission_denied" in src


class TestAlertQueue:
    """Engine callbacks (worker threads) queue alerts; _show_alert drains them
    on the main thread: notification + warning item + right settings pane."""

    def _app(self):
        return SimpleNamespace(_pending_alerts=[])

    def test_model_load_failed_queues_without_settings_url(self):
        app = self._app()
        WhisperMenuBarApp._on_model_load_failed(app, "download failed")
        [(subtitle, message, url)] = app._pending_alerts
        assert subtitle == "Model failed to load"
        assert "download failed" in message
        assert "Restart" in message  # actionable guidance
        assert url is None  # not permission-related: no menu item to reveal

    def test_permission_missing_queues_with_matching_pane(self):
        import whispy.ui.menu_bar as mb

        app = self._app()
        WhisperMenuBarApp._on_permission_missing(app, "microphone", "mic denied")
        WhisperMenuBarApp._on_permission_missing(app, "input_monitoring", "im denied")
        urls = [url for _, _, url in app._pending_alerts]
        assert urls == [
            mb._SETTINGS_URLS["microphone"],
            mb._SETTINGS_URLS["input_monitoring"],
        ]

    def test_injection_denied_targets_accessibility_pane(self):
        import whispy.ui.menu_bar as mb

        app = self._app()
        WhisperMenuBarApp._on_injection_denied(app, "1002")
        [(_, _, url)] = app._pending_alerts
        assert url == mb._SETTINGS_URLS["accessibility"]

    def test_show_alert_with_url_reveals_item_and_retargets_click(self, mocker):
        import whispy.ui.menu_bar as mb

        notify = mocker.patch.object(mb.rumps, "notification")
        app = SimpleNamespace(
            _set_permission_item_hidden=MagicMock(),
            _permission_settings_url=mb._SETTINGS_URLS["accessibility"],
        )

        WhisperMenuBarApp._show_alert(app, "Missing permission", "msg", mb._SETTINGS_URLS["microphone"])

        app._set_permission_item_hidden.assert_called_once_with(False)
        assert app._permission_settings_url == mb._SETTINGS_URLS["microphone"]
        notify.assert_called_once_with("Whispy", "Missing permission", "msg")

    def test_show_alert_without_url_only_notifies(self, mocker):
        import whispy.ui.menu_bar as mb

        notify = mocker.patch.object(mb.rumps, "notification")
        app = SimpleNamespace(
            _set_permission_item_hidden=MagicMock(),
            _permission_settings_url=mb._SETTINGS_URLS["accessibility"],
        )

        WhisperMenuBarApp._show_alert(app, "Model failed to load", "msg", None)

        app._set_permission_item_hidden.assert_not_called()
        assert app._permission_settings_url == mb._SETTINGS_URLS["accessibility"]
        notify.assert_called_once()

    def test_click_opens_most_recent_pane(self, mocker):
        import whispy.ui.menu_bar as mb

        popen = mocker.patch.object(mb.subprocess, "Popen")
        app = SimpleNamespace(_permission_settings_url=mb._SETTINGS_URLS["input_monitoring"])

        WhisperMenuBarApp._on_open_permission_settings(app, None)

        popen.assert_called_once_with(["open", mb._SETTINGS_URLS["input_monitoring"]])


class TestRecordingStopModelLoadingAlert:
    """_on_recording_stop warns when a dictation attempt raced the model load,
    instead of the previous silent no-op (nothing transcribed, no feedback).

    It hangs off the recording lifecycle rather than the trigger release so it
    fires when the *dictation* ends -- in toggle mode the key is released long
    before that, and the engine does not announce a release there at all.
    """

    def _app(self, model, model_loading):
        engine = SimpleNamespace(state=SimpleNamespace(model=model, model_loading=model_loading))
        return SimpleNamespace(engine=engine, _visualization=MagicMock(), _pending_alerts=[])

    def test_queues_alert_while_model_still_loading(self):
        app = self._app(model=None, model_loading=True)

        WhisperMenuBarApp._on_recording_stop(app)

        app._visualization.hide.assert_called_once_with()
        [(subtitle, message, url)] = app._pending_alerts
        assert subtitle == "Model still loading"
        assert "loading" in message.lower()
        assert url is None

    def test_no_alert_once_model_is_loaded(self):
        app = self._app(model=MagicMock(), model_loading=False)

        WhisperMenuBarApp._on_recording_stop(app)

        assert app._pending_alerts == []

    def test_no_alert_when_model_missing_but_not_loading(self):
        # e.g. the model failed to load — that already has its own dedicated
        # alert (on_model_load_failed); don't queue a second one here.
        app = self._app(model=None, model_loading=False)

        WhisperMenuBarApp._on_recording_stop(app)

        assert app._pending_alerts == []


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


class TestLaunchRegressions:
    """Startup crashes only reproducible under real rumps (mocked in this
    tier), guarded by source inspection — same pattern as TestAlertWiring."""

    def test_last_dark_assigned_before_anim_timer_starts(self):
        """_tick_anim reads _last_dark on its first tick; the attribute must
        exist before the timer is armed or a mid-init failure crashes ticks."""
        import inspect

        src = inspect.getsource(WhisperMenuBarApp.__init__)
        assert "_last_dark" in src.split("_anim_timer.start()")[0], (
            "_last_dark must be set before the anim timer starts"
        )


class TestPillLifecycleBelongsToTheRecording:
    """Regression (found in live-drive): in toggle mode the waveform pill vanished
    as soon as the keys were lifted, while the dictation was still running."""

    def _app(self):
        engine = SimpleNamespace(state=SimpleNamespace(model=MagicMock(), model_loading=False))
        return SimpleNamespace(engine=engine, _visualization=MagicMock(), _pending_alerts=[])

    def test_fn_released_only_hides_and_nothing_else(self):
        app = self._app()

        WhisperMenuBarApp._on_fn_released(app)

        app._visualization.hide.assert_called_once_with()
        assert app._pending_alerts == []

    def test_recording_start_shows_and_stop_hides(self):
        app = self._app()

        WhisperMenuBarApp._on_recording_start(app)
        app._visualization.show.assert_called_once_with()

        WhisperMenuBarApp._on_recording_stop(app)
        app._visualization.hide.assert_called_once_with()

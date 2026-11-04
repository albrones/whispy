"""Unit tests for the Linux adapters' mockable seams.

CI tier: the real pynput/xdotool/pystray seams are exercised only in the
`linux` real-seam tier. Here we cover the binary probe (xdotool-missing hint)
the Wayland-vs-X11 session detection and the Wayland adapters (wtype, the
compositor-bound trigger, the notification-only tray) with env/binaries patched.
"""

import sys
import threading
import time
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.platform.linux import injection as linux_injection
from whispy.platform.linux.injection import XdotoolInjector
from whispy.platform.linux.session import announce_wayland_mode, is_wayland_session


class TestXdotoolProbe:
    def test_missing_xdotool_emits_hint(self, mocker, capsys):
        mocker.patch.object(linux_injection.shutil, "which", return_value=None)
        XdotoolInjector()
        err = capsys.readouterr().err
        assert "xdotool not found" in err
        assert "install" in err.lower()

    def test_missing_xdotool_inject_is_noop(self, mocker):
        mocker.patch.object(linux_injection.shutil, "which", return_value=None)
        run = mocker.patch.object(linux_injection.subprocess, "run")
        injector = XdotoolInjector(copy_to_clipboard=False)
        injector.inject("hello")
        run.assert_not_called()

    def test_present_xdotool_no_hint(self, mocker, capsys):
        mocker.patch.object(linux_injection.shutil, "which", return_value="/usr/bin/xdotool")
        XdotoolInjector()
        assert "xdotool not found" not in capsys.readouterr().err

    def test_empty_text_is_noop(self, mocker):
        mocker.patch.object(linux_injection.shutil, "which", return_value="/usr/bin/xdotool")
        run = mocker.patch.object(linux_injection.subprocess, "run")
        injector = XdotoolInjector()
        injector.inject("")
        run.assert_not_called()


def _wait_until(predicate, timeout=2.0):
    """Poll ``predicate`` until it's truthy or the timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class TestInjectionOrdering:
    """Successive inject() calls are serialized in call order without blocking the caller."""

    def test_second_inject_waits_for_first_keystroke_injection(self, mocker):
        mocker.patch.object(linux_injection.shutil, "which", return_value="/usr/bin/xdotool")
        release_event = threading.Event()
        calls: list[list[str]] = []
        call_index = [0]

        def _run_side_effect(cmd, **kwargs):
            call_index[0] += 1
            calls.append(cmd)
            if call_index[0] == 1:
                release_event.wait(timeout=2.0)
            return mocker.Mock(returncode=0)

        run = mocker.patch.object(linux_injection.subprocess, "run", side_effect=_run_side_effect)

        injector = XdotoolInjector(copy_to_clipboard=False)
        injector.inject("A")
        injector.inject("B")

        # Wait for A's step to actually reach subprocess.run -- inject() itself
        # returns immediately, well before that happens.
        assert _wait_until(lambda: run.call_count >= 1)
        # inject() did not block the caller: we get here while the first
        # job is still parked on the event.
        assert not release_event.is_set()
        # B's step must not have been dispatched yet -- the worker is still
        # busy with A.
        assert run.call_count == 1

        release_event.set()
        assert _wait_until(lambda: run.call_count >= 2)
        # Keystroke mode passes the text as the trailing argv element.
        assert calls[0][-1] == "A"
        assert calls[1][-1] == "B"


class TestWaylandDetection:
    def test_wayland_via_session_type(self):
        assert is_wayland_session({"XDG_SESSION_TYPE": "wayland"}) is True

    def test_wayland_via_wayland_display(self):
        assert is_wayland_session({"WAYLAND_DISPLAY": "wayland-0"}) is True

    def test_x11_session_not_wayland(self):
        assert is_wayland_session({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) is False

    def test_empty_env_not_wayland(self):
        assert is_wayland_session({}) is False

    def test_wayland_mode_is_announced(self, caplog):
        caplog.set_level("INFO")
        assert announce_wayland_mode({"XDG_SESSION_TYPE": "wayland"}) is True
        assert "compositor" in caplog.text

    def test_x11_announces_nothing(self, caplog):
        caplog.set_level("INFO")
        assert announce_wayland_mode({"XDG_SESSION_TYPE": "x11"}) is False
        assert caplog.text == ""


class TestPynputHotkeyStart:
    """PynputHotkeyListener.start() resets held state."""

    def test_start_resets_held_flag(self):
        from whispy.platform.linux import hotkey as hk

        listener = hk.PynputHotkeyListener("ctrl_r")
        listener._held = True  # simulate a missed release leaving it latched
        listener.start()
        assert listener._held is False


class TestWaylandAdapterSelection:
    """detect() binds the Wayland adapters on a Wayland session, X11 ones otherwise."""

    def _adapters(self, mocker, wayland: bool):
        from whispy.platform.detect import detect
        from whispy.platform.linux import session

        mocker.patch.object(session, "is_wayland_session", return_value=wayland)
        mocker.patch.object(linux_injection.shutil, "which", return_value="/usr/bin/tool")
        return detect("linux")

    def test_wayland_binds_compositor_trigger_wtype_and_notification_tray(self, mocker):
        from whispy.platform.linux import hotkey, tray

        adapters = self._adapters(mocker, wayland=True)
        listener = adapters.make_hotkey_listener("ctrl_r", None, None)
        assert isinstance(listener, hotkey.CompositorBoundTrigger)
        listener.start()
        assert listener.active is False
        assert isinstance(adapters.make_text_injector(), linux_injection.WtypeInjector)
        assert isinstance(adapters.make_tray(mocker.Mock()), tray.NotificationOnlyTray)

    def test_x11_binds_pynput_xdotool_and_pystray(self, mocker):
        from whispy.platform.linux import hotkey, tray

        adapters = self._adapters(mocker, wayland=False)
        assert isinstance(adapters.make_hotkey_listener("ctrl_r", None, None), hotkey.PynputHotkeyListener)
        assert isinstance(adapters.make_text_injector(), XdotoolInjector)
        assert isinstance(adapters.make_tray(mocker.Mock()), tray.PystrayApp)


class TestWtypeInjector:
    def _injector(self, mocker, copy_to_clipboard, tools=("wtype", "wl-copy")):
        mocker.patch.object(
            linux_injection.shutil, "which", side_effect=lambda b: f"/usr/bin/{b}" if b in tools else None
        )
        run = mocker.patch.object(linux_injection.subprocess, "run", return_value=mocker.Mock(returncode=0))
        return linux_injection.WtypeInjector(copy_to_clipboard=copy_to_clipboard), run

    def test_keystroke_mode_types_from_stdin(self, mocker):
        injector, run = self._injector(mocker, copy_to_clipboard=False)
        injector.inject("-é è à ç")
        assert _wait_until(lambda: run.call_count == 1)
        assert run.call_args.args[0] == ["/usr/bin/wtype", "-"]
        assert run.call_args.kwargs["input"] == "-é è à ç".encode()
        assert run.call_args.kwargs["env"]["LC_ALL"] == "C.UTF-8"

    def test_wl_copy_streams_are_not_piped(self, mocker):
        # wl-copy's forked server inherits a piped stream and run() would block on it.
        injector, run = self._injector(mocker, copy_to_clipboard=True)
        injector.copy_only("x")
        assert _wait_until(lambda: run.call_count == 1)
        assert run.call_args.kwargs["stderr"] is linux_injection.subprocess.DEVNULL

    def test_clipboard_mode_copies_then_types(self, mocker):
        injector, run = self._injector(mocker, copy_to_clipboard=True)
        injector.inject("bonjour")
        assert _wait_until(lambda: run.call_count == 2)
        assert [c.args[0] for c in run.call_args_list] == [["/usr/bin/wl-copy"], ["/usr/bin/wtype", "-"]]

    def test_copy_only_never_types(self, mocker):
        injector, run = self._injector(mocker, copy_to_clipboard=True)
        injector.copy_only("long transcript")
        assert _wait_until(lambda: run.call_count == 1)
        assert run.call_args.args[0] == ["/usr/bin/wl-copy"]

    def test_missing_wtype_emits_hint_and_types_nothing(self, mocker, capsys):
        injector, run = self._injector(mocker, copy_to_clipboard=False, tools=())
        assert "wtype not found" in capsys.readouterr().err
        injector.inject("hello")
        time.sleep(0.05)
        run.assert_not_called()


class TestNotificationOnlyTray:
    def test_engine_errors_become_desktop_notifications(self, mocker):
        from whispy.platform.linux import tray

        popen = mocker.patch("subprocess.Popen")
        mocker.patch("shutil.which", return_value="/usr/bin/notify-send")
        engine = mocker.Mock()
        tray.NotificationOnlyTray(engine)
        on_limit = engine.on_recording_limit_reached.call_args.args[0]
        on_limit("Recording limit reached")
        assert popen.call_args.args[0][-1] == "Recording limit reached"

    def test_run_returns_once_quit(self, mocker):
        from whispy.platform.linux import tray

        app = tray.NotificationOnlyTray(mocker.Mock())
        runner = threading.Thread(target=app.run)
        runner.start()
        app.quit()
        runner.join(timeout=2)
        assert not runner.is_alive()


class _FakeKey:
    """Stand-in for a pynput ``Key`` enum member (special key)."""

    def __init__(self, name):
        self.name = name


class _FakeCharKey:
    """Stand-in for a pynput ``KeyCode`` (character key)."""

    def __init__(self, char):
        self.char = char


class TestSplitTriggerCombination:
    """Pure helper: split a combination string into (key_name, modifier_names)."""

    def test_plain_key_yields_empty_modifiers(self):
        from whispy.platform.linux.hotkey import split_trigger_combination

        assert split_trigger_combination("ctrl_r") == ("ctrl_r", frozenset())

    def test_combination_splits_key_and_modifiers(self):
        from whispy.platform.linux.hotkey import split_trigger_combination

        key_name, mods = split_trigger_combination("ctrl+alt+cmd+e")
        assert key_name == "e"
        assert mods == frozenset({"ctrl", "alt", "cmd"})

    def test_unknown_modifier_token_returns_none(self):
        from whispy.platform.linux.hotkey import split_trigger_combination

        assert split_trigger_combination("meta+e") is None

    def test_repeated_modifier_token_returns_none(self):
        from whispy.platform.linux.hotkey import split_trigger_combination

        assert split_trigger_combination("ctrl+ctrl+e") is None

    def test_trailing_plus_returns_none(self):
        from whispy.platform.linux.hotkey import split_trigger_combination

        assert split_trigger_combination("ctrl+") is None

    def test_non_string_returns_none(self):
        from whispy.platform.linux.hotkey import split_trigger_combination

        assert split_trigger_combination(63) is None


class TestPynputCombinationTrigger:
    """PynputHotkeyListener resolves a combination string and tracks held modifiers."""

    def test_default_single_key_trigger_still_fires_press_and_release(self, mocker):
        """Regression guard: the Linux default trigger IS a modifier key (ctrl_r) —
        it must still fire via decode_key_match, not be swallowed as "just a
        held modifier" by the new tracking added for combination triggers."""
        from whispy.platform.linux import hotkey as hk

        press = mocker.Mock()
        release = mocker.Mock()
        listener = hk.PynputHotkeyListener("ctrl_r", on_trigger_press=press, on_trigger_release=release)

        listener._on_press(_FakeKey("ctrl_r"))
        press.assert_called_once()
        listener._on_release(_FakeKey("ctrl_r"))
        release.assert_called_once()

    def test_combination_resolves_key_and_required_modifiers(self):
        from whispy.platform.linux import hotkey as hk

        listener = hk.PynputHotkeyListener("ctrl+alt+cmd+e")
        assert listener._trigger_key == "e"
        assert listener._required_modifiers == frozenset({"ctrl", "alt", "cmd"})

    def test_combination_press_requires_all_modifiers_held(self, mocker):
        from whispy.platform.linux import hotkey as hk

        press = mocker.Mock()
        listener = hk.PynputHotkeyListener("ctrl+alt+cmd+e", on_trigger_press=press)

        # Only ctrl held — "e" alone must not fire the trigger.
        listener._on_press(_FakeKey("ctrl_l"))
        listener._on_press(_FakeCharKey("e"))
        press.assert_not_called()

    def test_combination_press_fires_once_all_modifiers_held(self, mocker):
        from whispy.platform.linux import hotkey as hk

        press = mocker.Mock()
        listener = hk.PynputHotkeyListener("ctrl+alt+cmd+e", on_trigger_press=press)

        listener._on_press(_FakeKey("ctrl_l"))
        listener._on_press(_FakeKey("alt_l"))
        listener._on_press(_FakeKey("cmd"))
        listener._on_press(_FakeCharKey("e"))
        press.assert_called_once()

    def test_combination_release_fires_even_after_modifiers_released_first(self, mocker):
        """Same asymmetry as decode_key_match: release must not require the
        modifiers to still be held (users naturally release them first)."""
        from whispy.platform.linux import hotkey as hk

        press = mocker.Mock()
        release = mocker.Mock()
        listener = hk.PynputHotkeyListener("ctrl+alt+cmd+e", on_trigger_press=press, on_trigger_release=release)

        listener._on_press(_FakeKey("ctrl_l"))
        listener._on_press(_FakeKey("alt_l"))
        listener._on_press(_FakeKey("cmd"))
        listener._on_press(_FakeCharKey("e"))
        press.assert_called_once()

        listener._on_release(_FakeKey("ctrl_l"))
        listener._on_release(_FakeKey("alt_l"))
        listener._on_release(_FakeKey("cmd"))
        listener._on_release(_FakeCharKey("e"))
        release.assert_called_once()

    def test_start_clears_held_modifiers(self, mocker):
        from whispy.platform.linux import hotkey as hk

        listener = hk.PynputHotkeyListener("ctrl+alt+cmd+e")
        listener._held_modifiers = frozenset({"ctrl"})  # simulate a missed release
        listener.start()
        assert listener._held_modifiers == frozenset()

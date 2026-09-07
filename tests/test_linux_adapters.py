"""Unit tests for the Linux adapters' mockable seams.

CI tier: the real pynput/xdotool/pystray seams are exercised only in the
`linux` real-seam tier. Here we cover the binary probe (xdotool-missing hint)
and the Wayland-vs-X11 session detection with env/binaries patched.
"""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.platform.linux import injection as linux_injection
from whispy.platform.linux.injection import XdotoolInjector
from whispy.platform.linux.session import is_wayland_session, warn_if_wayland


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


class TestWaylandDetection:
    def test_wayland_via_session_type(self):
        assert is_wayland_session({"XDG_SESSION_TYPE": "wayland"}) is True

    def test_wayland_via_wayland_display(self):
        assert is_wayland_session({"WAYLAND_DISPLAY": "wayland-0"}) is True

    def test_x11_session_not_wayland(self):
        assert is_wayland_session({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) is False

    def test_empty_env_not_wayland(self):
        assert is_wayland_session({}) is False

    def test_warn_if_wayland_emits_message(self, capsys):
        warned = warn_if_wayland({"XDG_SESSION_TYPE": "wayland"})
        assert warned is True
        assert "X11 session" in capsys.readouterr().err

    def test_warn_if_x11_silent(self, capsys):
        warned = warn_if_wayland({"XDG_SESSION_TYPE": "x11"})
        assert warned is False
        assert capsys.readouterr().err == ""


class TestPynputHotkeyStart:
    """PynputHotkeyListener.start() resets held state and warns under Wayland."""

    def test_start_resets_held_flag(self, mocker):
        from whispy.platform.linux import hotkey as hk

        mocker.patch.object(hk, "is_wayland_session", return_value=False)
        listener = hk.PynputHotkeyListener("ctrl_r")
        listener._held = True  # simulate a missed release leaving it latched
        # pynput import/start is irrelevant here; force the early degrade path.
        mocker.patch.object(hk, "warn_if_wayland")
        listener.start()
        assert listener._held is False

    def test_start_warns_on_wayland(self, mocker):
        from whispy.platform.linux import hotkey as hk

        mocker.patch.object(hk, "is_wayland_session", return_value=True)
        warn = mocker.patch.object(hk, "warn_if_wayland")
        hk.PynputHotkeyListener("ctrl_r").start()
        warn.assert_called_once()

    def test_start_no_wayland_warning_on_x11(self, mocker):
        from whispy.platform.linux import hotkey as hk

        mocker.patch.object(hk, "is_wayland_session", return_value=False)
        warn = mocker.patch.object(hk, "warn_if_wayland")
        hk.PynputHotkeyListener("ctrl_r").start()
        warn.assert_not_called()


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

        mocker.patch.object(hk, "is_wayland_session", return_value=False)
        mocker.patch.object(hk, "warn_if_wayland")
        listener = hk.PynputHotkeyListener("ctrl+alt+cmd+e")
        listener._held_modifiers = frozenset({"ctrl"})  # simulate a missed release
        listener.start()
        assert listener._held_modifiers == frozenset()

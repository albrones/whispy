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

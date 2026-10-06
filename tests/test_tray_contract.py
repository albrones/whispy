"""Both tray apps satisfy the TrayUI port the daemon's SIGTERM handler uses.

`whispy_daemon.py` calls `app.quit()` from its SIGTERM handler. Neither
`PystrayApp` nor `WhisperMenuBarApp` had a `quit`, and the port only required
`run`, so `systemctl --user restart whispy` -- the documented Linux update
path -- died on an AttributeError inside the signal handler.
"""

from pathlib import Path

from whispy.platform.ports import TrayUI

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = ("run", "quit")


def test_the_port_requires_the_methods_the_daemon_calls():
    for name in REQUIRED:
        assert hasattr(TrayUI, name), f"TrayUI must declare {name}()"


def test_linux_tray_satisfies_the_port():
    from whispy.platform.linux.tray import PystrayApp

    for name in REQUIRED:
        assert callable(getattr(PystrayApp, name, None)), f"PystrayApp.{name} missing"


def test_macos_menu_bar_defines_quit():
    """Read the source: `rumps` is mocked session-wide, so the imported class
    is a MagicMock that answers `hasattr` for anything. `run` is inherited from
    `rumps.App`; `quit` is the one this class has to supply itself."""
    import ast

    tree = ast.parse((ROOT / "src" / "whispy" / "ui" / "menu_bar.py").read_text())
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "WhisperMenuBarApp")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "quit" in methods, "WhisperMenuBarApp must define quit() for the SIGTERM handler"


def test_quitting_the_linux_tray_stops_the_icon(mocker):
    from whispy.platform.linux.tray import PystrayApp

    app = PystrayApp.__new__(PystrayApp)
    app._icon = mocker.MagicMock()

    app.quit()

    app._icon.stop.assert_called_once()


def test_quitting_before_the_icon_exists_is_a_no_op():
    from whispy.platform.linux.tray import PystrayApp

    app = PystrayApp.__new__(PystrayApp)
    app._icon = None

    app.quit()  # SIGTERM can arrive before run() built the icon

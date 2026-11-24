"""Linux tray UI via pystray.

Surfaces Whispy's status and control actions (status, settings hint, quit) in
the system tray and reflects the recording state through the tray icon/title.
The macOS overlay windows are intentionally absent on Linux v1 — the overlay
hooks are no-ops here, so the engine drives the recording lifecycle identically
regardless of overlay presence.

pystray/Pillow are imported lazily inside ``run`` so importing this module never
requires the Linux GUI stack to be installed.

The tray must never block dictation: if it cannot start (no pystray backend, no
X display, a GTK error...), ``PystrayApp.run`` logs the reason, posts one
desktop notification and falls back to ``NotificationOnlyTray``. Setting
``"tray_icon": false`` in the config skips the tray entirely.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Tray colours by state: idle (grey), recording (red), busy/loading (amber).
_IDLE_RGB = (120, 120, 120)
_RECORDING_RGB = (220, 60, 60)
_BUSY_RGB = (220, 170, 60)


class PystrayApp:
    """pystray-backed tray app implementing the ``TrayUI`` port."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._icon = None
        self._fallback: NotificationOnlyTray | None = None
        self._quit_requested = threading.Event()
        self._pystray = None
        self._Image = None

        # The engine drives state through these; the tray reflects it. Overlay
        # hooks (fn pressed/released) are no-ops on Linux.
        engine.on_status_change(self._refresh)
        engine.on_recording_start(self._refresh)
        engine.on_recording_stop(self._refresh)
        # This file has no toast/notification mechanism (unlike the macOS menu
        # bar's rumps.notification): the tray only ever reflects status via its
        # icon/title/menu. Firing from a worker thread with nothing to marshal
        # onto, the best available surfacing is a stderr line, matching how the
        # rest of the Linux platform package (see platform/linux/hotkey.py)
        # degrades to a printed hint when there's no GUI affordance for it.
        engine.on_recording_limit_reached(self._on_recording_limit_reached)

    # -- State → visuals ---------------------------------------------------

    def _status_text(self) -> str:
        state = self.engine.state
        if state.model_loading:
            return "Loading model…"
        if state.model is None:
            return "⚠ Model not loaded"
        if state.is_recording:
            return "● Recording"
        if state.is_transcribing:
            return "Transcribing…"
        return "Ready"

    def _state_rgb(self) -> tuple[int, int, int]:
        state = self.engine.state
        if state.is_recording:
            return _RECORDING_RGB
        if state.is_transcribing or state.model_loading:
            return _BUSY_RGB
        return _IDLE_RGB

    def _make_image(self):
        img = self._Image.new("RGB", (64, 64), (0, 0, 0, 0))
        # A filled circle in the state colour; simple and theme-agnostic.
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 56, 56), fill=self._state_rgb())
        return img

    def _refresh(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.icon = self._make_image()
            self._icon.title = f"Whispy — {self._status_text()}"
            self._icon.update_menu()
        except Exception:
            pass

    def _on_recording_limit_reached(self, message: str) -> None:
        """Engine callback (worker thread): the recording hit its max duration
        and was stopped gracefully, its transcript copied to the clipboard.

        No notification path exists in this tray, so this surfaces as a stderr
        line rather than inventing a popup.
        """
        # ponytail: stderr only -- a user not watching the log never learns the
        # limit was hit. Upgrade path is a desktop notification (notify-send /
        # the org.freedesktop.Notifications D-Bus interface), which would also
        # give the Linux tray the capture-failed and permission alerts the macOS
        # menu bar already posts.
        print(f"[tray] {message}", file=sys.stderr)

    # -- Menu actions ------------------------------------------------------

    def _on_toggle_trigger_mode(self, _icon=None, _item=None) -> None:
        current = self.engine.state.config.get("trigger_mode", "hold")
        new_mode = "hold" if current == "toggle" else "toggle"
        self.engine.update_config({"trigger_mode": new_mode})
        self._refresh()

    def _on_quit(self, _icon=None, _item=None) -> None:
        try:
            self.engine.stop()
        except Exception:
            pass
        if self._icon is not None:
            self._icon.stop()

    def quit(self) -> None:
        """Stop the tray loop so the daemon can exit.

        The SIGTERM handler calls this, and on Linux SIGTERM is the documented
        update path (`systemctl --user restart whispy`). Without it the handler
        raised AttributeError and the process died on a traceback.
        """
        self._quit_requested.set()
        if self._icon is not None:
            self._icon.stop()
        if self._fallback is not None:
            self._fallback.quit()

    # -- Lifecycle ---------------------------------------------------------

    def run(self) -> None:
        """Build the tray icon and run the pystray loop (blocks).

        If the tray cannot start, keep the daemon alive in notification-only
        mode instead of raising. This only catches Python exceptions: a
        segfault inside GTK/appindicator kills the process, which is what the
        ``"tray_icon": false`` config opt-out is for.
        """
        try:
            self._run_icon()
        except Exception as exc:
            self._fall_back(exc)

    def _run_icon(self) -> None:
        import pystray
        from PIL import Image

        self._pystray = pystray
        self._Image = Image

        from ...core.config import get_default_config_path

        # Plain text labels only: pystray menus can't render attributed titles
        # or custom colours, so the brand-accent menu styling on macOS
        # (whispy.ui.menu_theme) has no Linux equivalent. This is intentional.
        menu = pystray.Menu(
            pystray.MenuItem(lambda _item: self._status_text(), None, enabled=False),
            pystray.MenuItem(f"Settings: {get_default_config_path()}", None, enabled=False),
            pystray.MenuItem(
                "Toggle mode",
                self._on_toggle_trigger_mode,
                checked=lambda _item: self.engine.state.config.get("trigger_mode", "hold") == "toggle",
            ),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon("whispy", self._make_image(), "Whispy", menu)
        self._icon.run()

    def _fall_back(self, exc: Exception) -> None:
        """The tray failed to start: warn once, then run notification-only."""
        self._icon = None
        logger.warning(
            'Tray icon unavailable (%s: %s); dictation keeps working. Set "tray_icon": false in '
            "~/.config/whispy/config.json to silence this.",
            type(exc).__name__,
            exc,
        )
        post_desktop_notification(
            "Whispy: no tray icon",
            f"Dictation still works; errors will show as notifications. Tray failed: {type(exc).__name__}.",
        )
        self._fallback = NotificationOnlyTray(self.engine)
        if self._quit_requested.is_set():
            return
        self._fallback.run()


def post_desktop_notification(title: str, body: str) -> None:
    """Show a desktop notification via ``notify-send``; stderr when it is absent."""
    import shutil
    import subprocess

    notify_send = shutil.which("notify-send")
    if not notify_send:
        print(f"[tray] {title}: {body}", file=sys.stderr)
        return
    subprocess.Popen(
        [notify_send, "--app-name=Whispy", title, body],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class NotificationOnlyTray:
    """Wayland ``TrayUI``: no icon, errors surface as desktop notifications.

    pystray's X11 icon is invisible in a Wayland bar (Waybar shows
    StatusNotifierItem icons, which pystray only offers through PyGObject +
    AppIndicator -- two system libraries for one icon). The compositor binding
    already gives the user the start/stop feedback, so this surface only has to
    keep the daemon's main thread alive and report what would otherwise fail
    unseen.

    X11 uses it too, in two cases: ``"tray_icon": false`` in the config, and as
    the automatic fallback when ``PystrayApp`` cannot start its tray icon.
    """

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._stopped = threading.Event()
        engine.on_recording_limit_reached(lambda message: post_desktop_notification("Whispy", message))
        engine.on_model_load_failed(lambda message: post_desktop_notification("Whispy: model not loaded", message))
        engine.on_capture_failed(lambda message: post_desktop_notification("Whispy: microphone", message))

    def run(self) -> None:
        """Block the main thread until ``quit`` (SIGTERM) is called."""
        self._stopped.wait()

    def quit(self) -> None:
        self._stopped.set()

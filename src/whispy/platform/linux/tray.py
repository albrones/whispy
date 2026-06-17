"""Linux tray UI via pystray.

Surfaces Whispy's status and control actions (status, settings hint, quit) in
the system tray and reflects the recording state through the tray icon/title.
The macOS overlay windows are intentionally absent on Linux v1 — the overlay
hooks are no-ops here, so the engine drives the recording lifecycle identically
regardless of overlay presence.

pystray/Pillow are imported lazily inside ``run`` so importing this module never
requires the Linux GUI stack to be installed.
"""

from __future__ import annotations

from typing import Any

# Tray colours by state: idle (grey), recording (red), busy/loading (amber).
_IDLE_RGB = (120, 120, 120)
_RECORDING_RGB = (220, 60, 60)
_BUSY_RGB = (220, 170, 60)


class PystrayApp:
    """pystray-backed tray app implementing the ``TrayUI`` port."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._icon = None
        self._pystray = None
        self._Image = None

        # The engine drives state through these; the tray reflects it. Overlay
        # hooks (fn pressed/released) are no-ops on Linux.
        engine.on_status_change(self._refresh)
        engine.on_recording_start(self._refresh)
        engine.on_recording_stop(self._refresh)

    # -- State → visuals ---------------------------------------------------

    def _status_text(self) -> str:
        state = self.engine.state
        if state.model_loading:
            return f"Loading model ({state.config['model_size']})…"
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

    # -- Menu actions ------------------------------------------------------

    def _on_quit(self, _icon=None, _item=None) -> None:
        try:
            self.engine.stop()
        except Exception:
            pass
        if self._icon is not None:
            self._icon.stop()

    # -- Lifecycle ---------------------------------------------------------

    def run(self) -> None:
        """Build the tray icon and run the pystray loop (blocks)."""
        import pystray
        from PIL import Image

        self._pystray = pystray
        self._Image = Image

        from ...core.config import get_default_config_path

        menu = pystray.Menu(
            pystray.MenuItem(lambda _item: self._status_text(), None, enabled=False),
            pystray.MenuItem(f"Settings: {get_default_config_path()}", None, enabled=False),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon("whispy", self._make_image(), "Whispy", menu)
        self._icon.run()

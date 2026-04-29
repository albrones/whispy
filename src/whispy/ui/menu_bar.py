"""Menu bar UI via rumps for status, animation, and settings."""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import rumps

from ..core.engine import (
    Engine,
    DEFAULT_CONFIG,
    MODEL_PRESETS,
    SUPPORTED_LANGUAGES,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
ICONS_DIR = SCRIPT_DIR / "icons"


class WhisperMenuBarApp(rumps.App):
    """Menu bar application for Whispy control and status display."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

        icon_path = (
            str(ICONS_DIR / "mic-idle.png")
            if (ICONS_DIR / "mic-idle.png").exists()
            else None
        )
        super().__init__(
            name="Whispy",
            icon=icon_path,
            template=True,
            quit_button=None,
        )
        if icon_path is None:
            self.title = "\U0001f3a4"

        self._recording_frame = 0
        self._idle_icon = icon_path
        self._transcribing_icon: Optional[str] = None
        self._load_icons()
        self._build_menu()

        # Register for status updates
        self.engine.on_status_change(self.update_status_display)

    def _load_icons(self) -> None:
        """Load icon paths for animation frames."""
        frame_names = [
            "mic-recording-1.png",
            "mic-recording-2.png",
            "mic-recording-3.png",
        ]
        self._recording_icons = []
        for name in frame_names:
            path = ICONS_DIR / name
            if path.exists():
                self._recording_icons.append(str(path))

        transcribing_path = ICONS_DIR / "mic-transcribing.png"
        if transcribing_path.exists():
            self._transcribing_icon = str(transcribing_path)

    def _build_menu(self) -> None:
        """Construct the full menu structure."""
        cfg = self.engine.state.config

        self.status_item = rumps.MenuItem("Ready", callback=None)
        self.status_item.set_callback(None)

        # Model selection
        self.model_menu = rumps.MenuItem("Model")
        self._model_items: Dict[str, rumps.MenuItem] = {}
        for key, preset in MODEL_PRESETS.items():
            item = rumps.MenuItem(preset["label"], callback=self._on_model_select)
            item._model_key = key
            if key == cfg["model_size"]:
                item.state = 1
            self._model_items[key] = item
            self.model_menu.add(item)

        # Language selection
        self.language_menu = rumps.MenuItem("Language")
        self._lang_items: Dict[str, rumps.MenuItem] = {}
        for code, label in SUPPORTED_LANGUAGES.items():
            item = rumps.MenuItem(label, callback=self._on_language_select)
            item._lang_code = code
            if code == cfg["language"]:
                item.state = 1
            self._lang_items[code] = item
            self.language_menu.add(item)

        # Clipboard toggle
        self.copy_menu = rumps.MenuItem(
            "Copy to clipboard", callback=self._on_toggle_copy
        )
        self.copy_menu.state = 1 if cfg.get("copy_to_clipboard", False) else 0

        # Fn listener status
        self.fn_status_item = rumps.MenuItem("Fn: —", callback=None)
        self.fn_status_item.set_callback(None)

        # Reload and quit
        self.reload_item = rumps.MenuItem("Restart", callback=self._on_reload)
        quit_item = rumps.MenuItem("Quit", callback=self._on_quit, key="q")

        self.menu = [
            self.status_item,
            None,
            self.model_menu,
            self.language_menu,
            self.copy_menu,
            None,
            self.fn_status_item,
            None,
            self.reload_item,
            quit_item,
        ]

    # -- Animation --

    @rumps.timer(0.2)
    def _animate(self, _sender: Any) -> None:
        if self.engine.state.is_recording and self._recording_icons:
            idx = self._recording_frame % len(self._recording_icons)
            self.icon = self._recording_icons[idx]
            self._recording_frame += 1
        elif self.engine.state.is_transcribing and self._transcribing_icon:
            self.icon = self._transcribing_icon
        else:
            if self._idle_icon:
                self.icon = self._idle_icon
            self._recording_frame = 0

    # -- Menu callbacks --

    def _on_model_select(self, sender: rumps.MenuItem) -> None:
        new_key = sender._model_key
        if new_key == self.engine.state.config["model_size"]:
            return
        for key, item in self._model_items.items():
            item.state = 1 if key == new_key else 0
        self.engine.update_config({"model_size": new_key})

    def _on_language_select(self, sender: rumps.MenuItem) -> None:
        new_code = sender._lang_code
        if new_code == self.engine.state.config["language"]:
            return
        for code, item in self._lang_items.items():
            item.state = 1 if code == new_code else 0
        self.engine.update_config({"language": new_code})

    def _on_toggle_copy(self, sender: rumps.MenuItem) -> None:
        new_state = 0 if sender.state == 1 else 1
        sender.state = new_state
        self.engine.update_config({"copy_to_clipboard": new_state == 1})

    def _on_reload(self, _sender: Any) -> None:
        script_path = ICONS_DIR.parent.parent / "whispy_daemon.py"
        if not script_path.exists():
            try:
                from AppKit import NSAlert

                alert = NSAlert.alloc().init()
                alert.setMessageText_("Restart file not found")
                alert.setInformativeText_(
                    f"Expected restart script at:\n{script_path}\n\n"
                    "Please reinstall Whispy."
                )
                alert.addButtonWithTitle_("OK")
                alert.runModal()
            except ImportError:
                print(
                    f"[menu] Restart script not found: {script_path}",
                    file=sys.stderr,
                )
            return
        subprocess.Popen([sys.executable, str(script_path)])
        rumps.quit_application()

    def _on_quit(self, _sender: Any) -> None:
        rumps.quit_application()

    # -- Status display --

    def update_status_display(self) -> None:
        """Refresh the status line in the menu."""
        if self.engine.state.model_loading:
            model_name = self.engine.state.config["model_size"]
            self.status_item.title = f"Loading model {model_name}..."
        elif self.engine.state.model is None:
            self.status_item.title = "\u26a0 Model not loaded"
        elif self.engine.state.is_recording:
            self.status_item.title = "\U0001f534 Recording..."
        elif self.engine.state.is_transcribing:
            self.status_item.title = "\u23f3 Transcribing..."
        else:
            self.status_item.title = "Ready"

        self.fn_status_item.title = "Trigger: Fn \u2713"

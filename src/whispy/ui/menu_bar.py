"""Menu bar UI via rumps for status, animation, and settings."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import rumps

from ..core.engine import (
    MODEL_PRESETS,
    SUPPORTED_LANGUAGES,
    Engine,
)
from .audio_level import AudioLevelMonitor
from .waveform_window import WaveformWindow

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
ICONS_DIR = SCRIPT_DIR / "icons"


class WhisperMenuBarApp(rumps.App):
    """Menu bar application for Whispy control and status display."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

        icon_path = str(ICONS_DIR / "mic-idle.png") if (ICONS_DIR / "mic-idle.png").exists() else None
        super().__init__(
            name="Whispy",
            icon=icon_path,
            template=True,
            quit_button=None,
        )
        if icon_path is None:
            self.title = "\U0001f3a4"

        self._idle_icon = icon_path
        self._build_menu()

        # Register for status updates
        self.engine.on_status_change(self.update_status_display)

        # Floating indicator window (always available, no external deps)
        from .indicator_window import IndicatorWindow

        self._indicator = IndicatorWindow()

        # Audio-reactive waveform visualization (replaces indicator during recording)
        self._audio_monitor = AudioLevelMonitor()
        self._visualization = WaveformWindow()
        self._visualization.set_audio_monitor(self._audio_monitor)

        self.engine.on_fn_pressed(self._on_fn_pressed)
        self.engine.on_fn_released(self._on_fn_released)
        self.engine.on_recording_start(self._on_recording_start)
        self.engine.on_recording_stop(self._on_recording_stop)

    def _build_menu(self) -> None:
        """Construct the full menu structure."""
        cfg = self.engine.state.config

        self.status_item = rumps.MenuItem("Ready", callback=None)
        self.status_item.set_callback(None)

        # Model selection
        self.model_menu = rumps.MenuItem("Model")
        self._model_items: dict[str, rumps.MenuItem] = {}
        for key, preset in MODEL_PRESETS.items():
            item = rumps.MenuItem(preset["label"], callback=self._on_model_select)
            item._model_key = key
            if key == cfg["model_size"]:
                item.state = 1
            self._model_items[key] = item
            self.model_menu.add(item)

        # Language selection
        self.language_menu = rumps.MenuItem("Language")
        self._lang_items: dict[str, rumps.MenuItem] = {}
        for code, label in SUPPORTED_LANGUAGES.items():
            item = rumps.MenuItem(label, callback=self._on_language_select)
            item._lang_code = code
            if code == cfg["language"]:
                item.state = 1
            self._lang_items[code] = item
            self.language_menu.add(item)

        # Clipboard toggle
        self.copy_menu = rumps.MenuItem("Copy to clipboard", callback=self._on_toggle_copy)
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

    # -- Indicator window callbacks --

    def _on_fn_pressed(self) -> None:
        """Show the waveform visualization when FN key is pressed."""
        if not self.engine.state.is_recording:
            self._indicator.hide()
            self._audio_monitor.start()
            self._visualization.show()

    def _on_fn_released(self) -> None:
        """Hide the waveform when FN is released."""
        self._audio_monitor.stop()
        self._visualization.hide()

    def _on_recording_start(self) -> None:
        """Start recording visualization and audio monitor."""
        self._indicator.hide()
        self._audio_monitor.start()
        self._visualization.show()

    def _on_recording_stop(self) -> None:
        """Stop the audio monitor and hide the waveform when recording ends."""
        self._audio_monitor.stop()
        self._visualization.hide()

    # -- Status display --

    def update_status_display(self) -> None:
        """Refresh the status line in the menu."""
        if self.engine._fn_pressed and not self.engine.state.is_recording:
            self.status_item.title = "Listening..."
        elif self.engine.state.model_loading:
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
                alert.setInformativeText_(f"Expected restart script at:\n{script_path}\n\nPlease reinstall Whispy.")
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
        self._audio_monitor.stop()
        self._visualization.destroy()
        self._indicator.destroy()
        rumps.quit_application()

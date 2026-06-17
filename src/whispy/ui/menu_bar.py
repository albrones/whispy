"""Menu bar UI via rumps for status, animation, and settings."""

import subprocess
import sys
from typing import Any

import rumps

from ..core.engine import (
    MODEL_PRESETS,
    SUPPORTED_LANGUAGES,
    Engine,
)
from ..core.paths import daemon_script_exists, resolve_daemon_script
from .audio_level import AudioLevelMonitor
from .unicode_anim import IDLE_FRAME, WAVEROWS_INTERVAL, select_frame
from .waveform_window import WaveformWindow


class WhisperMenuBarApp(rumps.App):
    """Menu bar application for Whispy control and status display."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

        # Menu bar identity is a unicode braille waveform shown as the title.
        # No image icon (auto-adapts to dark/light; animates only when active).
        super().__init__(
            name="Whispy",
            icon=None,
            quit_button=None,
        )
        self.title = IDLE_FRAME

        # Always-on timer (started on the main thread here so its NSTimer is
        # scheduled on the main run loop). It polls engine state each tick and
        # animates only while active — see _tick_anim. Starting/stopping a timer
        # from the engine's worker threads would schedule it on a thread with no
        # running run loop, so it would never fire.
        self._frame = 0
        self._anim_timer = rumps.Timer(self._tick_anim, WAVEROWS_INTERVAL)
        self._anim_timer.start()

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

        # Brand header (disabled label).
        header = rumps.MenuItem("Whispy · voice dictation")
        header.set_callback(None)

        self.status_item = rumps.MenuItem("Ready", callback=None)
        self.status_item.set_callback(None)

        # Settings section header (disabled label).
        settings_header = rumps.MenuItem("Settings")
        settings_header.set_callback(None)

        # Model selection — submenu title reflects the current choice; each item
        # shows its description (size / quality) alongside the label.
        self.model_menu = rumps.MenuItem("Model")
        self._model_items: dict[str, rumps.MenuItem] = {}
        for key, preset in MODEL_PRESETS.items():
            item = rumps.MenuItem(f"{preset['label']} — {preset['description']}", callback=self._on_model_select)
            item._model_key = key
            if key == cfg["model_size"]:
                item.state = 1
            self._model_items[key] = item
            self.model_menu.add(item)
        self._update_model_title()

        # Language selection — submenu title reflects the current choice.
        self.language_menu = rumps.MenuItem("Language")
        self._lang_items: dict[str, rumps.MenuItem] = {}
        for code, label in SUPPORTED_LANGUAGES.items():
            item = rumps.MenuItem(label, callback=self._on_language_select)
            item._lang_code = code
            if code == cfg["language"]:
                item.state = 1
            self._lang_items[code] = item
            self.language_menu.add(item)
        self._update_language_title()

        # Clipboard toggle
        self.copy_menu = rumps.MenuItem("Copy to clipboard", callback=self._on_toggle_copy)
        self.copy_menu.state = 1 if cfg.get("copy_to_clipboard", False) else 0

        # Usage hint (disabled label).
        self.fn_status_item = rumps.MenuItem("Hold Fn to dictate", callback=None)
        self.fn_status_item.set_callback(None)

        # Reload and quit
        self.reload_item = rumps.MenuItem("Restart", callback=self._on_reload)
        quit_item = rumps.MenuItem("Quit", callback=self._on_quit, key="q")

        self.menu = [
            header,
            self.status_item,
            None,
            settings_header,
            self.model_menu,
            self.language_menu,
            self.copy_menu,
            None,
            self.fn_status_item,
            None,
            self.reload_item,
            quit_item,
        ]

    def _update_model_title(self) -> None:
        cur = self.engine.state.config["model_size"]
        label = MODEL_PRESETS.get(cur, {}).get("label", cur)
        self.model_menu.title = f"Model: {label}"

    def _update_language_title(self) -> None:
        cur = self.engine.state.config["language"]
        self.language_menu.title = f"Language: {SUPPORTED_LANGUAGES.get(cur, cur)}"

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

    # -- Menu bar animation --

    def _is_active(self) -> bool:
        """True while Whispy is listening, recording, transcribing, or loading."""
        state = self.engine.state
        return (
            self.engine._fn_pressed
            or state.is_recording
            or state.is_transcribing
            or state.model_loading
        )

    def _tick_anim(self, _timer: Any) -> None:
        """Poll state every tick; scroll the waverows wave only while active."""
        if self._is_active():
            self.title = select_frame(self._frame, is_active=True)
            self._frame += 1
        else:
            self._frame = 0
            if self.title != IDLE_FRAME:
                self.title = select_frame(0, is_active=False)

    # -- Status display --

    def update_status_display(self) -> None:
        """Refresh the status line (the menu bar title is driven by _tick_anim)."""
        state = self.engine.state
        if self.engine._fn_pressed and not state.is_recording:
            self.status_item.title = "Listening\u2026"
        elif state.model_loading:
            model_name = state.config["model_size"]
            self.status_item.title = f"Loading model ({model_name})\u2026"
        elif state.model is None:
            self.status_item.title = "\u26a0 Model not loaded"
        elif state.is_recording:
            self.status_item.title = "\u25cf Recording"
        elif state.is_transcribing:
            self.status_item.title = "Transcribing\u2026"
        else:
            self.status_item.title = "Ready"

    # -- Menu callbacks --

    def _on_model_select(self, sender: rumps.MenuItem) -> None:
        new_key = sender._model_key
        if new_key == self.engine.state.config["model_size"]:
            return
        for key, item in self._model_items.items():
            item.state = 1 if key == new_key else 0
        self.engine.update_config({"model_size": new_key})
        self._update_model_title()

    def _on_language_select(self, sender: rumps.MenuItem) -> None:
        new_code = sender._lang_code
        if new_code == self.engine.state.config["language"]:
            return
        for code, item in self._lang_items.items():
            item.state = 1 if code == new_code else 0
        self.engine.update_config({"language": new_code})
        self._update_language_title()

    def _on_toggle_copy(self, sender: rumps.MenuItem) -> None:
        new_state = 0 if sender.state == 1 else 1
        sender.state = new_state
        self.engine.update_config({"copy_to_clipboard": new_state == 1})

    def _on_reload(self, _sender: Any) -> None:
        script_path = resolve_daemon_script()
        if not daemon_script_exists(script_path):
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
        self._anim_timer.stop()
        self._audio_monitor.stop()
        self._visualization.destroy()
        self._indicator.destroy()
        rumps.quit_application()

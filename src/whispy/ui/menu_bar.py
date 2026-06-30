"""Menu bar UI via rumps for status, animation, and settings."""

import subprocess
import sys
from typing import Any

import rumps
from AppKit import NSThread
from PyObjCTools import AppHelper

from ..core.engine import (
    MODEL_PRESETS,
    SUPPORTED_LANGUAGES,
    TRIGGER_PRESETS,
    Engine,
)
from ..core.paths import daemon_script_exists, resolve_app_bundle, resolve_daemon_script
from ..hardware.event_decode import keycode_to_name
from ..platform.macos import login_item
from . import menu_theme
from .unicode_anim import IDLE_FRAME, WAVEROWS_INTERVAL, select_frame
from .waveform_window import WaveformWindow

# Detached relaunch waiter for Restart. Run as `python -c <this> <cmd> <args...>`:
# it polls the :9090 single-instance lock until the quitting instance releases
# it (connection refused), then launches the replacement. This outlives the
# instance that spawns it, so the new daemon never races the old one onto a
# fallback port. ~5 s timeout then launches anyway, so a wedged old process
# can't strand the user without Whispy.
_RELAUNCH_WAITER = (
    "import socket,subprocess,sys,time\n"
    "deadline=time.time()+5.0\n"
    "while time.time()<deadline:\n"
    "    s=socket.socket(); s.settimeout(0.25)\n"
    "    try:\n"
    "        s.connect(('127.0.0.1',9090))\n"
    "    except OSError:\n"
    "        break\n"  # refused → port free → old instance gone
    "    else:\n"
    "        s.close(); time.sleep(0.2)\n"  # still listening → keep waiting
    "subprocess.Popen(sys.argv[1:])\n"
)


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

        # Set by the engine's injection-denied callback (fired off a worker
        # thread); drained on the main run loop in _tick_anim so all UI calls
        # (notification + menu mutation) happen on the main thread.
        self._pending_perm_message: str | None = None

        self._build_menu()

        # Cache the appearance the accents were built for, so _tick_anim can
        # rebuild them when the user flips light/dark while the app is running.
        self._last_dark = menu_theme.is_dark_appearance()

        # Register for status updates
        self.engine.on_status_change(self.update_status_display)
        self.engine.on_injection_permission_denied(self._on_injection_denied)

        # Audio-reactive waveform visualization shown during recording. The
        # level comes from the engine's single capture stream (engine.get_level)
        # — never a second mic stream, which would make capture deliver silent
        # buffers.
        self._visualization = WaveformWindow()
        self._visualization.set_audio_monitor(self.engine)

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
        menu_theme.apply_title(self.status_item, menu_theme.status_title("Ready"))

        # Permission warning — hidden until a keystroke is denied. Clicking it
        # opens the relevant System Settings pane.
        self.permission_item = rumps.MenuItem(
            "⚠ Can't type — fix permissions…",
            callback=self._on_open_accessibility_settings,
        )
        self._set_permission_item_hidden(True)

        # Settings section header (disabled label).
        settings_header = rumps.MenuItem("Settings")
        settings_header.set_callback(None)
        self._settings_header = settings_header
        menu_theme.apply_title(settings_header, menu_theme.section_title("Settings"))

        # Model selection — submenu title reflects the current choice; each item
        # shows its description (size / quality) alongside the label.
        self.model_menu = rumps.MenuItem("Model")
        self._model_items: dict[str, rumps.MenuItem] = {}
        for key, preset in MODEL_PRESETS.items():
            label = f"{preset['label']} — {preset['description']}"
            item = rumps.MenuItem(label, callback=self._on_model_select)
            item._model_key = key
            item._label = label
            menu_theme.apply_title(item, menu_theme.check_title(label, key == cfg["model_size"]))
            self._model_items[key] = item
            self.model_menu.add(item)
        self._update_model_title()

        # Language selection — submenu title reflects the current choice.
        self.language_menu = rumps.MenuItem("Language")
        self._lang_items: dict[str, rumps.MenuItem] = {}
        for code, label in SUPPORTED_LANGUAGES.items():
            item = rumps.MenuItem(label, callback=self._on_language_select)
            item._lang_code = code
            item._label = label
            menu_theme.apply_title(item, menu_theme.check_title(label, code == cfg["language"]))
            self._lang_items[code] = item
            self.language_menu.add(item)
        self._update_language_title()

        # Clipboard toggle — trailing check so the title aligns left with the
        # Model/Language rows. (Streaming is always on; no toggle.)
        self.copy_menu = rumps.MenuItem("Copy to clipboard", callback=self._on_toggle_copy)
        self.copy_menu._label = "Copy to clipboard"
        menu_theme.apply_title(
            self.copy_menu, menu_theme.toggle_title("Copy to clipboard", cfg.get("copy_to_clipboard", False))
        )

        # Trigger (push-to-talk key) selection — submenu title reflects the
        # current choice, each item shows a check, mirroring Model/Language.
        self.trigger_menu = rumps.MenuItem("Trigger")
        self._trigger_items: list[rumps.MenuItem] = []
        for label, value in TRIGGER_PRESETS:
            item = rumps.MenuItem(label, callback=self._on_trigger_select)
            item._trigger_value = value
            item._label = label
            menu_theme.apply_title(item, menu_theme.check_title(label, self._trigger_is_active(value)))
            self._trigger_items.append(item)
            self.trigger_menu.add(item)
        self._update_trigger_title()

        # Start at login (macOS .app bundle only). SMAppService.mainAppService
        # registers the *running bundle*, so this is meaningful only when we run
        # from a .app and the framework is available (macOS 13+). The loose
        # script path autostarts via its LaunchAgent instead, so hide it there.
        # State is a persisted setting (cfg["start_at_login"]); the OS
        # registration is reconciled to it below.
        self.login_item_menu = None
        if resolve_app_bundle() is not None and login_item.available():
            self._reconcile_login_item(cfg.get("start_at_login", False))
            self.login_item_menu = rumps.MenuItem("Start at login", callback=self._on_toggle_login_item)
            self.login_item_menu._label = "Start at login"
            menu_theme.apply_title(
                self.login_item_menu,
                menu_theme.toggle_title("Start at login", cfg.get("start_at_login", False)),
            )

        # Reload and quit
        self.reload_item = rumps.MenuItem("Restart", callback=self._on_reload)
        quit_item = rumps.MenuItem("Quit", callback=self._on_quit, key="q")

        self.menu = [
            header,
            self.status_item,
            self.permission_item,
            None,
            settings_header,
            self.model_menu,
            self.language_menu,
            self.copy_menu,
            self.trigger_menu,
            *([self.login_item_menu] if self.login_item_menu is not None else []),
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

    def _trigger_is_active(self, value: int | None) -> bool:
        """True if the given preset value matches the configured trigger.

        Fn (the platform default) is stored as None, so an unset/empty config
        trigger matches it; other presets match their raw keycode.
        """
        cur = self.engine.state.config.get("trigger")
        if value is None:
            return cur in (None, "")
        return cur == value

    def _trigger_label(self) -> str:
        """Human label for the active trigger: a preset label if one matches,
        else the keycode's name (covers a hand-edited config value)."""
        cur = self.engine.state.config.get("trigger")
        for label, value in TRIGGER_PRESETS:
            if self._trigger_is_active(value):
                return label
        if isinstance(cur, int):
            return keycode_to_name(cur)
        return str(cur)

    def _update_trigger_title(self) -> None:
        self.trigger_menu.title = f"Trigger: {self._trigger_label()}"

    def _refresh_accents(self) -> None:
        """Rebuild every accented title for the current appearance.

        Called when the system appearance flips so the brand green is re-picked
        (bright on dark, dim on light). Reads current config for check state.
        """
        cfg = self.engine.state.config
        menu_theme.apply_title(self._settings_header, menu_theme.section_title("Settings"))
        for key, item in self._model_items.items():
            menu_theme.apply_title(item, menu_theme.check_title(item._label, key == cfg["model_size"]))
        for code, item in self._lang_items.items():
            menu_theme.apply_title(item, menu_theme.check_title(item._label, code == cfg["language"]))
        menu_theme.apply_title(
            self.copy_menu, menu_theme.toggle_title(self.copy_menu._label, cfg.get("copy_to_clipboard", False))
        )
        for item in self._trigger_items:
            menu_theme.apply_title(item, menu_theme.check_title(item._label, self._trigger_is_active(item._trigger_value)))
        # Status line carries the green dot; rebuilding it re-reads the appearance.
        self.update_status_display()

    # -- Indicator window callbacks --

    def _on_fn_pressed(self) -> None:
        """Show the waveform visualization when FN key is pressed."""
        if not self.engine.state.is_recording:
            self._visualization.show()

    def _on_fn_released(self) -> None:
        """Hide the waveform when FN is released."""
        self._visualization.hide()

    def _on_recording_start(self) -> None:
        """Show the recording waveform (level comes from the capture stream)."""
        self._visualization.show()

    def _on_recording_stop(self) -> None:
        """Hide the waveform when recording ends."""
        self._visualization.hide()

    # -- Menu bar animation --

    def _is_active(self) -> bool:
        """True while Whispy is listening, recording, transcribing, or loading."""
        state = self.engine.state
        return self.engine._fn_pressed or state.is_recording or state.is_transcribing or state.model_loading

    def _tick_anim(self, _timer: Any) -> None:
        """Poll state every tick; scroll the waverows wave only while active."""
        # Drain a queued permission warning on the main thread (the engine fires
        # the callback from an injection worker thread).
        if self._pending_perm_message is not None:
            message = self._pending_perm_message
            self._pending_perm_message = None
            self._show_permission_warning(message)
        # Re-read the system appearance and rebuild accents only when it flips,
        # so green text/glyphs stay legible after a light/dark switch.
        dark_now = menu_theme.is_dark_appearance()
        if dark_now != self._last_dark:
            self._last_dark = dark_now
            self._refresh_accents()
        if self._is_active():
            self.title = select_frame(self._frame, is_active=True)
            self._frame += 1
        else:
            self._frame = 0
            if self.title != IDLE_FRAME:
                self.title = select_frame(0, is_active=False)

    # -- Permission warning --

    def _on_injection_denied(self, message: str) -> None:
        """Engine callback (worker thread): queue the warning for the main thread."""
        self._pending_perm_message = message

    def _set_permission_item_hidden(self, hidden: bool) -> None:
        """Toggle the warning menu item via its underlying NSMenuItem."""
        ns_item = getattr(self.permission_item, "_menuitem", None)
        if ns_item is not None:
            ns_item.setHidden_(hidden)

    def _show_permission_warning(self, message: str) -> None:
        """Reveal the warning menu item and post a notification (main thread)."""
        self._set_permission_item_hidden(False)
        try:
            rumps.notification("Whispy", "Can't type into apps", message)
        except Exception:
            # Notifications require a bundled app / Info.plist; ignore if absent.
            pass

    def _on_open_accessibility_settings(self, _sender: Any) -> None:
        """Open the Accessibility pane of System Settings."""
        subprocess.Popen(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ]
        )

    # -- Status display --

    def update_status_display(self) -> None:
        """Refresh the status line, marshaling to the main thread.

        Registered as ``engine.on_status_change``, which fires from the event-tap
        and transcription-worker threads. AppKit must only be mutated on the main
        thread, so hop to the main run loop when called off it (mirrors
        ``WaveformWindow``).
        """
        if NSThread.isMainThread():
            self._update_status_on_main()
        else:
            AppHelper.callAfter(self._update_status_on_main)

    def _update_status_on_main(self) -> None:
        """Rebuild the status line title (main thread only)."""
        state = self.engine.state
        if self.engine._fn_pressed and not state.is_recording:
            text = "Listening\u2026"
        elif state.model_loading:
            model_name = state.config["model_size"]
            text = f"Loading model ({model_name})\u2026"
        elif state.model is None:
            text = "\u26a0 Model not loaded"
        elif state.is_recording:
            # The green status dot is supplied by status_title; no inline \u25cf here.
            text = "Recording"
        elif state.is_transcribing:
            text = "Transcribing\u2026"
        else:
            text = "Ready"
        menu_theme.apply_title(self.status_item, menu_theme.status_title(text))

    # -- Menu callbacks --

    def _on_model_select(self, sender: rumps.MenuItem) -> None:
        new_key = sender._model_key
        if new_key == self.engine.state.config["model_size"]:
            return
        for key, item in self._model_items.items():
            menu_theme.apply_title(item, menu_theme.check_title(item._label, key == new_key))
        # Persist and apply live: a model change needs the new model loaded now,
        # not only on next restart (mirrors the HTTP /config path).
        needs_reload = self.engine.update_config({"model_size": new_key})
        if needs_reload:
            from ..core.engine import load_model_async

            load_model_async(self.engine)
        self._update_model_title()

    def _on_language_select(self, sender: rumps.MenuItem) -> None:
        new_code = sender._lang_code
        if new_code == self.engine.state.config["language"]:
            return
        for code, item in self._lang_items.items():
            menu_theme.apply_title(item, menu_theme.check_title(item._label, code == new_code))
        self.engine.update_config({"language": new_code})
        self._update_language_title()

    def _on_trigger_select(self, sender: rumps.MenuItem) -> None:
        new_value = sender._trigger_value
        if self._trigger_is_active(new_value):
            return
        # Persist and apply live: update_config restarts the listener so the new
        # push-to-talk key works now, not only after a Restart.
        self.engine.update_config({"trigger": new_value})
        for item in self._trigger_items:
            menu_theme.apply_title(item, menu_theme.check_title(item._label, self._trigger_is_active(item._trigger_value)))
        self._update_trigger_title()

    def _on_toggle_copy(self, sender: rumps.MenuItem) -> None:
        enabled = not self.engine.state.config.get("copy_to_clipboard", False)
        menu_theme.apply_title(sender, menu_theme.toggle_title(sender._label, enabled))
        self.engine.update_config({"copy_to_clipboard": enabled})

    @staticmethod
    def _reconcile_login_item(want_enabled: bool) -> None:
        """Sync the OS login-item registration to the persisted setting."""
        if want_enabled and not login_item.is_enabled():
            login_item.enable()
        elif not want_enabled and login_item.is_enabled():
            login_item.disable()

    def _on_toggle_login_item(self, sender: rumps.MenuItem) -> None:
        # Persisted setting: flip config, then sync the OS registration to it.
        enabled = not self.engine.state.config.get("start_at_login", False)
        self.engine.update_config({"start_at_login": enabled})
        if enabled:
            login_item.enable()
        else:
            login_item.disable()
        menu_theme.apply_title(sender, menu_theme.toggle_title(sender._label, enabled))

    def _on_reload(self, _sender: Any) -> None:
        # Restart hands the :9090 single-instance lock from this instance to the
        # replacement without overlap: a detached waiter polls until we release
        # the port, then launches. We must NOT force a parallel instance
        # (no `open -n`) — with the port fallback gone, a racing new instance
        # would fail to bind rather than drift, so sequencing is required.
        bundle = resolve_app_bundle()
        if bundle is not None:
            # Inside Whispy.app the daemon is not a loose file; relaunch the
            # whole bundle. Plain `open` (not `-n`) launches it once we've quit.
            launch = ["/usr/bin/open", str(bundle)]
        else:
            # Source-tree / venv run: re-exec the daemon entry-point script.
            script_path = resolve_daemon_script()
            if not daemon_script_exists(script_path):
                try:
                    from AppKit import NSAlert

                    alert = NSAlert.alloc().init()
                    alert.setMessageText_("Restart file not found")
                    alert.setInformativeText_(
                        f"Expected restart script at:\n{script_path}\n\nPlease reinstall Whispy."
                    )
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
                except ImportError:
                    print(
                        f"[menu] Restart script not found: {script_path}",
                        file=sys.stderr,
                    )
                return
            launch = [sys.executable, str(script_path)]

        # Spawn the detached waiter first so it outlives this instance, then quit
        # to release the lock; the waiter relaunches once the port is free.
        subprocess.Popen([sys.executable, "-c", _RELAUNCH_WAITER, *launch])
        rumps.quit_application()

    def _on_quit(self, _sender: Any) -> None:
        self._anim_timer.stop()
        self._visualization.destroy()
        rumps.quit_application()

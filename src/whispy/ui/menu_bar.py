"""Menu bar UI via rumps for status, animation, and settings."""

import subprocess
import sys
from typing import Any

import rumps
from AppKit import NSThread
from PyObjCTools import AppHelper

from ..core.engine import (
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

# System Settings deep links per permission kind (engine on_permission_missing).
_SETTINGS_URL_BASE = "x-apple.systempreferences:com.apple.preference.security"
_SETTINGS_URLS = {
    "microphone": f"{_SETTINGS_URL_BASE}?Privacy_Microphone",
    "input_monitoring": f"{_SETTINGS_URL_BASE}?Privacy_ListenEvent",
    "accessibility": f"{_SETTINGS_URL_BASE}?Privacy_Accessibility",
    "automation": f"{_SETTINGS_URL_BASE}?Privacy_Automation",
}


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
        # Cache the appearance the accents were built for BEFORE the timer can
        # fire: _tick_anim reads _last_dark on its first tick.
        self._last_dark = menu_theme.is_dark_appearance()

        self._anim_timer = rumps.Timer(self._tick_anim, WAVEROWS_INTERVAL)
        self._anim_timer.start()

        # Alerts queued by engine callbacks (fired off worker threads); drained
        # on the main run loop in _tick_anim so all UI calls (notification +
        # menu mutation) happen on the main thread. Each entry is
        # (subtitle, message, settings_url) — settings_url is the System
        # Settings pane the warning menu item should open, or None when the
        # alert is not permission-related (no menu item to reveal).
        self._pending_alerts: list[tuple[str, str, str | None]] = []
        self._permission_settings_url = _SETTINGS_URLS["accessibility"]

        self._build_menu()

        # Register for status updates
        self.engine.on_status_change(self.update_status_display)
        self.engine.on_injection_permission_denied(self._on_injection_denied)
        self.engine.on_permission_missing(self._on_permission_missing)
        self.engine.on_model_load_failed(self._on_model_load_failed)
        self.engine.on_capture_failed(self._on_capture_failed)

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

        # Permission warning — hidden until a permission problem is detected
        # (startup probe or inject-time denial). Clicking it opens the System
        # Settings pane of the most recent problem.
        self.permission_item = rumps.MenuItem(
            "⚠ Missing permission — fix in System Settings…",
            callback=self._on_open_permission_settings,
        )
        self._set_permission_item_hidden(True)

        # Settings section header (disabled label).
        settings_header = rumps.MenuItem("Settings")
        settings_header.set_callback(None)
        self._settings_header = settings_header
        menu_theme.apply_title(settings_header, menu_theme.section_title("Settings"))

        # Model and Language submenus are gone with the Whisper backend:
        # Parakeet ships in one size and detects language itself, so neither
        # would configure anything.

        # Clipboard toggle — trailing check so the title aligns left with the
        # Trigger row. (Streaming is always on; no toggle.)
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
            self.copy_menu,
            self.trigger_menu,
            *([self.login_item_menu] if self.login_item_menu is not None else []),
            None,
            self.reload_item,
            quit_item,
        ]

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
        menu_theme.apply_title(
            self.copy_menu, menu_theme.toggle_title(self.copy_menu._label, cfg.get("copy_to_clipboard", False))
        )
        for item in self._trigger_items:
            menu_theme.apply_title(
                item, menu_theme.check_title(item._label, self._trigger_is_active(item._trigger_value))
            )
        # Status line carries the green dot; rebuilding it re-reads the appearance.
        self.update_status_display()

    # -- Indicator window callbacks --

    def _on_fn_pressed(self) -> None:
        """Show the waveform visualization when FN key is pressed."""
        if not self.engine.state.is_recording:
            self._visualization.show()

    def _on_fn_released(self) -> None:
        """Hide the waveform when FN is released.

        Also warns when the dictation was pointless: the model is still
        loading, so run_transcription would have silently produced nothing.
        """
        self._visualization.hide()
        if self.engine.state.model is None and self.engine.state.model_loading:
            self._pending_alerts.append(
                (
                    "Model still loading",
                    "Whispy is still loading the transcription model — try again in a moment.",
                    None,
                )
            )

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
        # Drain queued alerts on the main thread (engine callbacks fire from
        # worker threads).
        while self._pending_alerts:
            self._show_alert(*self._pending_alerts.pop(0))
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

    # -- Alerts (permission warnings, model-load failure) --

    def _on_injection_denied(self, message: str) -> None:
        """Engine callback (worker thread): queue the warning for the main thread."""
        self._pending_alerts.append(("Can't type into apps", message, _SETTINGS_URLS["accessibility"]))

    def _on_permission_missing(self, kind: str, message: str) -> None:
        """Engine callback (worker thread): a startup permission probe reported
        an explicit denial."""
        url = _SETTINGS_URLS.get(kind, _SETTINGS_URLS["accessibility"])
        self._pending_alerts.append(("Missing permission", message, url))

    def _on_model_load_failed(self, message: str) -> None:
        """Engine callback (worker thread): the transcription model failed to
        load — without this, every dictation silently returns nothing."""
        self._pending_alerts.append(
            (
                "Model failed to load",
                f"{message} — check your internet connection, then use Restart from the Whispy menu.",
                None,
            )
        )

    def _on_capture_failed(self, message: str) -> None:
        """Engine callback (worker thread): the capture stream could not be
        opened — the recording runs but no audio is being captured."""
        self._pending_alerts.append(
            (
                "No microphone available",
                f"{message} — check your input device, then try again.",
                None,
            )
        )

    def _set_permission_item_hidden(self, hidden: bool) -> None:
        """Toggle the warning menu item via its underlying NSMenuItem."""
        ns_item = getattr(self.permission_item, "_menuitem", None)
        if ns_item is not None:
            ns_item.setHidden_(hidden)

    def _show_alert(self, subtitle: str, message: str, settings_url: str | None) -> None:
        """Post a notification; for permission alerts also reveal the warning
        menu item and point its click at the right settings pane (main thread)."""
        if settings_url is not None:
            self._permission_settings_url = settings_url
            self._set_permission_item_hidden(False)
        try:
            rumps.notification("Whispy", subtitle, message)
        except Exception:
            # Notifications require a bundled app / Info.plist; ignore if absent.
            pass

    def _on_open_permission_settings(self, _sender: Any) -> None:
        """Open the System Settings pane of the most recent permission alert."""
        subprocess.Popen(["open", self._permission_settings_url])

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
            text = "Loading model\u2026"
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

    def _on_trigger_select(self, sender: rumps.MenuItem) -> None:
        new_value = sender._trigger_value
        if self._trigger_is_active(new_value):
            return
        # Persist and apply live: update_config restarts the listener so the new
        # push-to-talk key works now, not only after a Restart.
        self.engine.update_config({"trigger": new_value})
        for item in self._trigger_items:
            menu_theme.apply_title(
                item, menu_theme.check_title(item._label, self._trigger_is_active(item._trigger_value))
            )
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
                    alert.setInformativeText_(f"Expected restart script at:\n{script_path}\n\nPlease reinstall Whispy.")
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

#!/usr/bin/env python3
"""Whisper Dictation — macOS menu bar speech-to-text daemon.

Push-to-talk via Fn key (native CGEventTap or Karabiner fallback).
HTTP API on localhost:9090 for external control.
Menu bar UI via rumps for status, animation, and settings.
"""

import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import rumps
from faster_whisper import WhisperModel

# ---------------------------------------------------------------------------
# Paths & defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ICONS_DIR = SCRIPT_DIR / "icons"
CONFIG_DIR = Path.home() / ".config" / "whisper-dictation"
CONFIG_PATH = CONFIG_DIR / "config.json"
RECORDING_PATH = os.path.join(tempfile.gettempdir(), "whisper-dictation.wav")
PORT = 9090

FN_KEYCODE = 63
NX_SECONDARYFNMASK = 0x800000
QUARTZ_AVAILABLE = False

try:
    from Quartz import (
        CGEventTapCreate,
        CGEventMaskBit,
        kCGEventFlagsChanged,
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        kCGKeyboardEventKeycode,
        CFMachPortCreateRunLoopSource,
        CFRunLoopGetCurrent,
        CFRunLoopAddSource,
        kCFRunLoopDefaultMode,
        CGEventTapEnable,
        CFRunLoopRun,
    )

    QUARTZ_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Model presets — displayed in Settings menu
# ---------------------------------------------------------------------------
MODEL_PRESETS = {
    "tiny": {
        "label": "Rapide (tiny)",
        "description": "75 Mo — le plus rapide, qualité limitée",
    },
    "base": {"label": "Léger (base)", "description": "142 Mo — bon compromis vitesse"},
    "small": {"label": "Normal (small)", "description": "466 Mo — recommandé"},
    "medium": {"label": "Précis (medium)", "description": "1.5 Go — meilleure qualité"},
    "large-v3": {
        "label": "Maximum (large)",
        "description": "2.9 Go — qualité maximale, lent",
    },
}

COMPUTE_OPTIONS = {
    "cpu-int8": {
        "label": "CPU — int8 (recommandé)",
        "device": "cpu",
        "compute_type": "int8",
        "description": "Optimal pour Apple Silicon. Utilise le CPU avec quantisation int8.",
    },
    "cpu-float32": {
        "label": "CPU — float32",
        "device": "cpu",
        "compute_type": "float32",
        "description": "CPU pleine précision. Plus lent, légèrement plus précis.",
    },
    "cuda-float16": {
        "label": "GPU — float16 (NVIDIA uniquement)",
        "device": "cuda",
        "compute_type": "float16",
        "description": "GPU NVIDIA CUDA. Non disponible sur macOS.",
    },
    "cuda-int8": {
        "label": "GPU — int8 (NVIDIA uniquement)",
        "device": "cuda",
        "compute_type": "int8_float16",
        "description": "GPU NVIDIA avec quantisation mixte. Non disponible sur macOS.",
    },
}

DEFAULT_CONFIG = {
    "model_size": "small",
    "compute_key": "cpu-int8",
    "language": "fr",
    "beam_size": 1,
    "best_of": 2,
}


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------
def load_config() -> dict:
    """Load config from disk, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            config.update({k: saved[k] for k in saved if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[config] Failed to load {CONFIG_PATH}: {exc}", file=sys.stderr)
    return config


def save_config(config: dict) -> None:
    """Persist config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except OSError as exc:
        print(f"[config] Failed to save {CONFIG_PATH}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Dictation state (shared between threads)
# ---------------------------------------------------------------------------
class DictationState:
    def __init__(self):
        self.recording_process = None
        self.is_recording = False
        self.is_transcribing = False
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self.fn_listener_active = False
        self.last_transcription = None
        self.model: WhisperModel | None = None
        self.model_loading = False
        self.config = load_config()
        self.app: "WhisperMenuBarApp | None" = None


state = DictationState()


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def _load_model(config: dict) -> WhisperModel:
    """Instantiate WhisperModel from config dict."""
    compute = COMPUTE_OPTIONS.get(config["compute_key"], COMPUTE_OPTIONS["cpu-int8"])
    cpu_threads = 0
    if compute["device"] == "cpu":
        try:
            cpu_threads = max(2, os.cpu_count() // 2)
        except (TypeError, AttributeError):
            cpu_threads = 4
    return WhisperModel(
        config["model_size"],
        device=compute["device"],
        compute_type=compute["compute_type"],
        cpu_threads=cpu_threads,
    )


def load_model_async() -> None:
    """Load the whisper model in a background thread. Updates state + menu bar."""

    def _worker():
        state.model_loading = True
        _update_app_status()
        try:
            model_name = state.config["model_size"]
            compute_key = state.config["compute_key"]
            print(f"[model] Loading '{model_name}' with compute '{compute_key}'...")
            new_model = _load_model(state.config)
            state.model = new_model
            print(f"[model] Loaded successfully")
        except Exception as exc:
            print(f"[model] Error loading model: {exc}", file=sys.stderr)
            state.model = None
        finally:
            state.model_loading = False
            _update_app_status()

    threading.Thread(target=_worker, name="model-loader", daemon=True).start()


def _update_app_status():
    """Notify the menu bar app to refresh its display."""
    if state.app:
        try:
            state.app.update_status_display()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def start_recording():
    with state.lock:
        if state.is_recording:
            return False
        state.recording_process = subprocess.Popen(
            ["sox", "-d", "-r", "16000", "-c", "1", RECORDING_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        state.is_recording = True
    _update_app_status()
    return True


def stop_recording_and_transcribe():
    """Synchronous stop + transcribe — used by HTTP POST /stop."""
    with state.lock:
        if not state.is_recording:
            return None
        state.is_recording = False
        proc = state.recording_process
        state.recording_process = None
    _update_app_status()

    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    if not os.path.exists(RECORDING_PATH):
        return None

    state.is_transcribing = True
    _update_app_status()

    text = transcribe(RECORDING_PATH)
    try:
        os.remove(RECORDING_PATH)
    except OSError:
        pass

    state.is_transcribing = False
    if text:
        state.last_transcription = text
        type_text(text)
    _update_app_status()
    return text


def stop_recording_async():
    """Called from CGEventTap callback — must return fast, no blocking."""
    with state.lock:
        if not state.is_recording:
            return
        state.is_recording = False
        proc = state.recording_process
        state.recording_process = None
    _update_app_status()
    if proc and proc.poll() is None:
        proc.terminate()
    state._stop_event.set()


def _transcription_worker():
    """Dedicated thread: waits for Fn release, then runs transcription."""
    while True:
        state._stop_event.wait()
        state._stop_event.clear()
        if not os.path.exists(RECORDING_PATH):
            continue

        state.is_transcribing = True
        _update_app_status()

        text = transcribe(RECORDING_PATH)
        try:
            os.remove(RECORDING_PATH)
        except OSError:
            pass

        state.is_transcribing = False
        if text:
            state.last_transcription = text
            type_text(text)
        _update_app_status()

        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Pop.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


# ---------------------------------------------------------------------------
# Transcription & text injection
# ---------------------------------------------------------------------------
def transcribe(audio_path):
    if state.model is None:
        print("[transcribe] Model not loaded, skipping", file=sys.stderr)
        return None
    try:
        cfg = state.config
        segments, _info = state.model.transcribe(
            audio_path,
            language=cfg.get("language", "fr"),
            beam_size=cfg.get("beam_size", 1),
            best_of=cfg.get("best_of", 2),
        )
        text_parts = [seg.text.strip() for seg in segments]
        text = " ".join(text_parts)
        return text if text else None
    except Exception as exc:
        print(f"[transcribe] Error: {exc}", file=sys.stderr)
        return None


def type_text(text):
    escaped = text.replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'set the clipboard to "{escaped}"',
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        timeout=5,
    )


def play_sound(sound_name):
    subprocess.Popen(
        ["afplay", f"/System/Library/Sounds/{sound_name}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Fn key listener (CGEventTap — native, no Karabiner needed)
# ---------------------------------------------------------------------------
def _fn_event_callback(proxy, event_type, event, refcon):
    if event_type == kCGEventFlagsChanged:
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        if keycode == FN_KEYCODE:
            flags = CGEventGetFlags(event)
            if flags & NX_SECONDARYFNMASK:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Tink.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                start_recording()
            else:
                stop_recording_async()
    return event


def start_fn_listener():
    if not QUARTZ_AVAILABLE:
        print(
            "[dictation] pyobjc-framework-Quartz not installed — Fn key detection disabled.\n"
            "  Install with: pip install pyobjc-framework-Quartz",
            file=sys.stderr,
        )
        return
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        CGEventMaskBit(kCGEventFlagsChanged),
        _fn_event_callback,
        None,
    )
    if tap is None:
        print(
            "[dictation] CGEventTapCreate failed — grant Input Monitoring to python3:\n"
            "  System Settings → Privacy & Security → Input Monitoring → add python3\n"
            "  Then restart: launchctl kickstart -k gui/$(id -u)/com.whisper-dictation",
            file=sys.stderr,
        )
        return

    source = CFMachPortCreateRunLoopSource(None, tap, 0)

    def _run():
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopDefaultMode)
        CGEventTapEnable(tap, True)
        state.fn_listener_active = True
        print("[dictation] Fn key listener active (CGEventTap)")
        CFRunLoopRun()

    threading.Thread(target=_run, name="fn-event-tap", daemon=True).start()


# ---------------------------------------------------------------------------
# HTTP server (backward-compatible + new endpoints)
# ---------------------------------------------------------------------------
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            self._json_response(
                200,
                {
                    "recording": state.is_recording,
                    "transcribing": state.is_transcribing,
                    "fn_listener": state.fn_listener_active,
                    "model_loaded": state.model is not None,
                    "model_loading": state.model_loading,
                },
            )
        elif self.path == "/config":
            self._json_response(200, state.config)
        elif self.path == "/last-transcription":
            self._json_response(200, {"text": state.last_transcription})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/start":
            play_sound("Tink.aiff")
            start_recording()
            self._json_response(200, {"status": "recording"})

        elif self.path == "/stop":
            text = stop_recording_and_transcribe()
            play_sound("Pop.aiff")
            self._json_response(200, {"status": "done", "text": text})

        elif self.path == "/stop-async":
            stop_recording_async()
            self._json_response(200, {"status": "stopping"})

        elif self.path == "/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                for key in body:
                    if key in DEFAULT_CONFIG:
                        state.config[key] = body[key]
                save_config(state.config)
                needs_reload = any(k in body for k in ("model_size", "compute_key"))
                if needs_reload:
                    load_model_async()
                self._json_response(200, {"status": "ok", "config": state.config})
            except (json.JSONDecodeError, ValueError) as exc:
                self._json_response(400, {"error": str(exc)})

        else:
            self._json_response(404, {"error": "not found"})

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        print(f"[http] {fmt % args}")


def start_http_server():
    """Start HTTP server in a daemon thread."""
    server = HTTPServer(("127.0.0.1", PORT), RequestHandler)

    def _serve():
        print(f"[http] Listening on 127.0.0.1:{PORT}")
        server.serve_forever()

    thread = threading.Thread(target=_serve, name="http-server", daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------------------
# Menu bar application (rumps)
# ---------------------------------------------------------------------------
class WhisperMenuBarApp(rumps.App):
    def __init__(self):
        icon_path = (
            str(ICONS_DIR / "mic-idle.png")
            if (ICONS_DIR / "mic-idle.png").exists()
            else None
        )
        super().__init__(
            name="Whisper Dictation",
            icon=icon_path,
            template=True,
            quit_button=None,
        )
        if icon_path is None:
            self.title = "🎤"

        self._recording_frame = 0
        self._recording_icons = []
        self._idle_icon = icon_path
        self._transcribing_icon = None
        self._load_icons()
        self._build_menu()

    def _load_icons(self):
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

    def _build_menu(self):
        """Construct the full menu structure."""
        cfg = state.config

        self.status_item = rumps.MenuItem("Prêt", callback=None)
        self.status_item.set_callback(None)

        self.model_menu = rumps.MenuItem("Modèle")
        self._model_items = {}
        for key, preset in MODEL_PRESETS.items():
            item = rumps.MenuItem(preset["label"], callback=self._on_model_select)
            item._model_key = key
            if key == cfg["model_size"]:
                item.state = 1
            self._model_items[key] = item
            self.model_menu.add(item)

        self.compute_menu = rumps.MenuItem("Calcul")
        self._compute_items = {}
        is_apple_silicon = (
            platform.processor() == "arm" or platform.machine() == "arm64"
        )
        for key, opt in COMPUTE_OPTIONS.items():
            label = opt["label"]
            if is_apple_silicon and key == "cpu-int8":
                label += " ⭐"
            item = rumps.MenuItem(label, callback=self._on_compute_select)
            item._compute_key = key
            if key == cfg["compute_key"]:
                item.state = 1
            if "cuda" in key and sys.platform == "darwin":
                item.set_callback(None)
                item.title = f"{label} (indisponible)"
            self._compute_items[key] = item
            self.compute_menu.add(item)

        self.fn_status_item = rumps.MenuItem("Fn: —", callback=None)
        self.fn_status_item.set_callback(None)

        quit_item = rumps.MenuItem("Quitter", callback=self._on_quit, key="q")

        self.menu = [
            self.status_item,
            None,
            self.model_menu,
            self.compute_menu,
            None,
            self.fn_status_item,
            None,
            quit_item,
        ]

    @rumps.timer(0.2)
    def _animate(self, _sender):
        if state.is_recording and self._recording_icons:
            idx = self._recording_frame % len(self._recording_icons)
            self.icon = self._recording_icons[idx]
            self._recording_frame += 1
        elif state.is_transcribing and self._transcribing_icon:
            self.icon = self._transcribing_icon
        else:
            if self._idle_icon:
                self.icon = self._idle_icon
            self._recording_frame = 0

    def _on_model_select(self, sender):
        """User selected a model size."""
        new_key = sender._model_key
        if new_key == state.config["model_size"]:
            return

        for key, item in self._model_items.items():
            item.state = 1 if key == new_key else 0

        state.config["model_size"] = new_key
        save_config(state.config)
        load_model_async()

    def _on_compute_select(self, sender):
        """User selected a compute option."""
        new_key = sender._compute_key
        if new_key == state.config["compute_key"]:
            return

        for key, item in self._compute_items.items():
            item.state = 1 if key == new_key else 0

        state.config["compute_key"] = new_key
        save_config(state.config)
        load_model_async()

    def _on_quit(self, _sender):
        rumps.quit_application()

    def update_status_display(self):
        """Refresh the status line in the menu."""
        if state.model_loading:
            model_name = state.config["model_size"]
            self.status_item.title = f"Chargement du modèle {model_name}…"
        elif state.model is None:
            self.status_item.title = "⚠ Modèle non chargé"
        elif state.is_recording:
            self.status_item.title = "🔴 Enregistrement…"
        elif state.is_transcribing:
            self.status_item.title = "⏳ Transcription…"
        else:
            self.status_item.title = "Prêt"

        if state.fn_listener_active:
            self.fn_status_item.title = "Fn: ✓ actif"
        elif QUARTZ_AVAILABLE:
            self.fn_status_item.title = "Fn: ✗ inactif (vérifier permissions)"
        else:
            self.fn_status_item.title = "Fn: — (pyobjc non installé)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    app = WhisperMenuBarApp()
    state.app = app

    load_model_async()

    threading.Thread(
        target=_transcription_worker, name="transcription-worker", daemon=True
    ).start()

    start_fn_listener()

    http_server = start_http_server()

    def _handle_sigterm(*_args):
        http_server.shutdown()
        rumps.quit_application()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    print("[main] Whisper Dictation starting (menu bar mode)")
    app.run()

    http_server.shutdown()
    print("[main] Daemon stopped.")


if __name__ == "__main__":
    main()

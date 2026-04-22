"""HTTP API server for external control and status monitoring.

Provides RESTful endpoints for:
- Status checks (GET /status, /config, /last-transcription)
- Manual control (POST /start, /stop, /stop-async)
- Configuration management (POST /config)
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from ..core.audio import RECORDING_PATH
from ..core.engine import (
    Engine,
    DEFAULT_CONFIG,
    load_config,
    save_config,
)

PORT = 9090


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Whispy control API."""

    # Engine instance — set by start_http_server before serving
    engine: Optional[Engine] = None

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/status":
            self._json_response(200, self.engine.get_status())
        elif self.path == "/config":
            self._json_response(200, self.engine.state.config)
        elif self.path == "/last-transcription":
            self._json_response(200, {"text": self.engine.state.last_transcription})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        """Handle POST requests."""
        if self.path == "/start":
            self.engine.start_recording()
            self._play_sound("Tink.aiff")
            self._json_response(200, {"status": "recording"})

        elif self.path == "/stop":
            text = self._sync_stop_and_transcribe()
            self._play_sound("Pop.aiff")
            self._json_response(200, {"status": "done", "text": text})

        elif self.path == "/stop-async":
            self.engine.stop_recording()
            self.engine.state._stop_event.set()
            self._json_response(200, {"status": "stopping"})

        elif self.path == "/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                needs_reload = self.engine.update_config(body)
                if needs_reload:
                    from ..core.engine import load_model_async

                    load_model_async(self.engine)
                self._json_response(
                    200, {"status": "ok", "config": self.engine.state.config}
                )
            except (json.JSONDecodeError, ValueError) as exc:
                self._json_response(400, {"error": str(exc)})

        else:
            self._json_response(404, {"error": "not found"})

    def _sync_stop_and_transcribe(self) -> Optional[str]:
        """Stop recording and transcribe synchronously (for /stop endpoint)."""
        import subprocess
        import os

        with self.engine.state.lock:
            if not self.engine.state.is_recording:
                return None
            self.engine.state.is_recording = False
            proc = self.engine.state.recording_process
            self.engine.state.recording_process = None

        self.engine._notify_status_change()

        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        if not os.path.exists(RECORDING_PATH):
            return None

        self.engine.state.is_transcribing = True
        self.engine._notify_status_change()

        text = self.engine.run_transcription()

        self.engine.state.is_transcribing = False
        self.engine._notify_status_change()
        return text

    def _play_sound(self, sound_name: str) -> None:
        """Play a system sound."""
        import subprocess

        threading.Thread(
            target=lambda: subprocess.Popen(
                ["afplay", f"/System/Library/Sounds/{sound_name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
            daemon=True,
        ).start()

    def _json_response(self, code: int, data: Dict[str, Any]) -> None:
        """Send a JSON HTTP response."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt: str, *args: Any) -> None:
        """Log HTTP requests."""
        print(f"[http] {fmt % args}")


def start_http_server(engine: Engine) -> HTTPServer:
    """Start HTTP server in a daemon thread."""
    RequestHandler.engine = engine
    server = HTTPServer(("127.0.0.1", PORT), RequestHandler)

    def _serve() -> None:
        print(f"[http] Listening on 127.0.0.1:{PORT}")
        server.serve_forever()

    threading.Thread(target=_serve, name="http-server", daemon=True).start()
    return server

"""HTTP API server for external control and status monitoring.

Provides RESTful endpoints for:
- Status checks (GET /status, /config, /last-transcription)
- Manual control (POST /start, /stop, /stop-async)
- Configuration management (POST /config)
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from ..core.audio import RECORDING_PATH
from ..core.engine import (
    Engine,
)

PORT = 9090


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Whispy control API."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        engine = self.server.engine
        if self.path == "/status":
            self._json_response(200, engine.get_status())
        elif self.path == "/config":
            self._json_response(200, engine.state.config)
        elif self.path == "/last-transcription":
            self._json_response(200, {"text": engine.state.last_transcription})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        """Handle POST requests."""
        engine = self.server.engine
        if self.path == "/start":
            engine.start_recording()
            engine._notifier.recording_started()
            self._json_response(200, {"status": "recording"})

        elif self.path == "/stop":
            text = self._sync_stop_and_transcribe(engine)
            engine._notifier.transcription_succeeded()
            self._json_response(200, {"status": "done", "text": text})

        elif self.path == "/stop-async":
            engine.stop_recording()
            # Wake the transcription worker. The attribute is `stop_event`
            # (not `_stop_event`); the old name raised AttributeError -> 500.
            engine.state.stop_event.set()
            self._json_response(200, {"status": "stopping"})

        elif self.path == "/transcribe-file":
            # Deterministic seam for validation: transcribe a known WAV with the
            # current config (no mic, no keystroke injection, no file deletion).
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                path = body.get("path")
                if not path:
                    self._json_response(400, {"error": "missing 'path'"})
                    return
                text = engine.transcribe_file(path)
                if text is None:
                    self._json_response(409, {"error": "model not loaded or file missing", "path": path})
                    return
                self._json_response(200, {"text": text})
            except (json.JSONDecodeError, ValueError) as exc:
                self._json_response(400, {"error": str(exc)})

        elif self.path == "/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}

                # Reject deprecated config keys
                if "trigger_key" in body:
                    self._json_response(400, {"error": "trigger_key is no longer configurable"})
                    return
                if "compute_key" in body:
                    self._json_response(400, {"error": "compute_key is no longer configurable"})
                    return

                needs_reload = engine.update_config(body)
                if needs_reload:
                    from ..core.engine import load_model_async

                    load_model_async(engine)
                self._json_response(200, {"status": "ok", "config": engine.state.config})
            except (json.JSONDecodeError, ValueError) as exc:
                self._json_response(400, {"error": str(exc)})

        else:
            self._json_response(404, {"error": "not found"})

    def _sync_stop_and_transcribe(self, engine: Engine) -> str | None:
        """Stop recording and transcribe synchronously (for /stop endpoint)."""
        import os

        # Properly transition FSM through RECORDING -> TRANSCRIBING
        # AudioEngine.stop() handles capture teardown + FSM transition
        engine._audio_engine.stop()

        engine.state.is_recording = False
        engine._notify_status_change()

        engine.state.is_transcribing = True
        engine._notify_status_change()

        if not os.path.exists(RECORDING_PATH):
            engine._state_machine.transcription_complete()
            engine.state.is_transcribing = False
            engine._notify_status_change()
            return None

        text = engine.run_transcription()

        engine._state_machine.transcription_complete()
        engine.state.is_transcribing = False
        engine._notify_status_change()
        return text

    def _json_response(self, code: int, data: dict[str, Any]) -> None:
        """Send a JSON HTTP response."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt: str, *args: Any) -> None:
        """Log HTTP requests."""
        print(f"[http] {fmt % args}")


def start_http_server(engine: Engine, start_port: int = PORT, max_attempts: int = 10) -> HTTPServer:
    """Start HTTP server in a daemon thread, trying consecutive ports if needed."""
    for port in range(start_port, start_port + max_attempts):
        try:
            server = HTTPServer(("127.0.0.1", port), RequestHandler)
            server.engine = engine

            def _serve(p=port, srv=server):
                print(f"[http] Listening on 127.0.0.1:{p}")
                srv.serve_forever()

            threading.Thread(target=_serve, name="http-server", daemon=True).start()
            return server
        except OSError:
            pass

    raise OSError(f"Could not bind to any port from {start_port} to {start_port + max_attempts - 1}")

"""HTTP API server for external control and status monitoring.

Provides RESTful endpoints for:
- Status checks (GET /status, /config, /last-transcription)
- Manual control (POST /start, /stop, /stop-async)
- Configuration management (POST /config)
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from ..core.auth import AUTH_HEADER, AUTH_SCHEME
from ..core.engine import (
    Engine,
)
from ..core.paths import transcribe_allow_dir

PORT = 9090

# Reject request bodies larger than this before reading them — an unauthenticated
# (or pre-auth) client must not be able to force an unbounded allocation.
MAX_BODY_BYTES = 64 * 1024


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Whispy control API."""

    def _authorized(self) -> bool:
        """Gate every request: reject browser-originated, rebinding, and
        unauthenticated callers.

        Loopback is not a boundary against the browser, so before any side
        effect we (1) pin the ``Host`` header to ``127.0.0.1``/``localhost`` at
        our port (DNS-rebinding defense), (2) reject any request carrying an
        ``Origin``/``Referer`` (native clients send neither; browsers always
        do), and (3) require the per-install bearer token. On rejection we send
        the response and return ``False`` so the caller stops.
        """
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in allowed_hosts:
            self._json_response(403, {"error": "forbidden host"})
            return False

        # A native CLI/app client never sets Origin/Referer; a browser fetch
        # always does. Presence => the request came from a web page.
        if self.headers.get("Origin") is not None or self.headers.get("Referer") is not None:
            self._json_response(403, {"error": "forbidden origin"})
            return False

        expected = getattr(self.server, "auth_token", None)
        if expected:
            header = self.headers.get(AUTH_HEADER, "")
            prefix = f"{AUTH_SCHEME} "
            presented = header[len(prefix) :] if header.startswith(prefix) else ""
            # Constant-time compare to avoid leaking the token via timing.
            import hmac

            if not presented or not hmac.compare_digest(presented, expected):
                self._json_response(401, {"error": "unauthorized"})
                return False
        return True

    def _read_body(self) -> dict | None:
        """Read and JSON-parse a request body, capping its size first.

        Returns the parsed dict (``{}`` when empty). On an oversized body sends
        ``413`` and returns ``None``; on invalid JSON sends ``400`` and returns
        ``None``. Callers must stop when ``None`` is returned.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._json_response(400, {"error": "invalid Content-Length"})
            return None
        if length > MAX_BODY_BYTES:
            self._json_response(413, {"error": "request body too large"})
            return None
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError) as exc:
            self._json_response(400, {"error": str(exc)})
            return None

    def do_GET(self) -> None:
        """Handle GET requests."""
        if not self._authorized():
            return
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
        if not self._authorized():
            return
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
            body = self._read_body()
            if body is None:
                return
            path = body.get("path")
            if not path:
                self._json_response(400, {"error": "missing 'path'"})
                return
            # Restrict to the allow-listed fixtures dir: an authenticated caller
            # still must not be able to probe/read arbitrary filesystem paths.
            allow_dir = getattr(self.server, "allow_dir", None) or transcribe_allow_dir()
            try:
                resolved = Path(path).resolve()
                resolved.relative_to(Path(allow_dir).resolve())
            except (ValueError, OSError):
                self._json_response(403, {"error": "path not allowed"})
                return
            text = engine.transcribe_file(str(resolved))
            if text is None:
                self._json_response(409, {"error": "model not loaded or file missing", "path": path})
                return
            self._json_response(200, {"text": text})

        elif self.path == "/stream-file":
            # Deterministic streaming seam: replay a known WAV through live
            # segmentation + per-chunk transcription (no mic, no inject, no
            # delete). Returns the ordered chunk texts so validation can verify
            # chunking without a microphone.
            body = self._read_body()
            if body is None:
                return
            path = body.get("path")
            if not path:
                self._json_response(400, {"error": "missing 'path'"})
                return
            allow_dir = getattr(self.server, "allow_dir", None) or transcribe_allow_dir()
            try:
                resolved = Path(path).resolve()
                resolved.relative_to(Path(allow_dir).resolve())
            except (ValueError, OSError):
                self._json_response(403, {"error": "path not allowed"})
                return
            try:
                texts = engine.stream_file(str(resolved))
            except Exception as exc:
                # Never drop the connection on an internal error — return 500 so
                # the caller sees a clear failure instead of a closed socket.
                self._json_response(500, {"error": f"stream-file failed: {exc}"})
                return
            if texts is None:
                self._json_response(409, {"error": "model not loaded or file missing", "path": path})
                return
            self._json_response(200, {"texts": texts, "text": " ".join(texts)})

        elif self.path == "/config":
            body = self._read_body()
            if body is None:
                return

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

        path = engine._audio_engine.recording_path
        if not path or not os.path.exists(path):
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


def start_http_server(
    engine: Engine,
    auth_token: str | None = None,
    start_port: int = PORT,
    max_attempts: int = 10,
) -> HTTPServer:
    """Start HTTP server in a daemon thread, trying consecutive ports if needed.

    ``auth_token`` is the per-install secret required on every request; when set,
    unauthenticated callers are rejected with ``401``.
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            server = HTTPServer(("127.0.0.1", port), RequestHandler)
            server.engine = engine
            server.auth_token = auth_token
            server.allow_dir = transcribe_allow_dir()

            def _serve(p=port, srv=server):
                print(f"[http] Listening on 127.0.0.1:{p}")
                srv.serve_forever()

            threading.Thread(target=_serve, name="http-server", daemon=True).start()
            return server
        except OSError:
            pass

    raise OSError(f"Could not bind to any port from {start_port} to {start_port + max_attempts - 1}")

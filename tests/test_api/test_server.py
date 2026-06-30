"""Tests for the HTTP API server endpoints.

Uses a real HTTP server with a mock engine to test endpoint behavior.
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest.mock import MagicMock

import pytest

from whispy.api.server import RequestHandler
from whispy.core.engine import DictationState, Engine


def _find_free_port():
    """Find a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def test_server(mocker, tmp_path):
    """Start a test HTTP server with a mock Engine."""
    # Point recording at a temp file that already exceeds the readiness
    # threshold so AudioEngine.start() returns immediately instead of waiting
    # the full cold-start timeout.
    import whispy.core.audio as audio_module

    recording_file = tmp_path / "whispy.wav"
    recording_file.write_bytes(b"\x00" * 6000)
    mocker.patch.object(audio_module, "RECORDING_PATH", str(recording_file))

    ds = DictationState()
    engine = Engine(ds)

    # Mock subprocess for sound playback and recording
    mock_popen = mocker.patch("subprocess.Popen")
    mock_instance = MagicMock()
    mock_instance.poll.return_value = None
    mock_popen.return_value = mock_instance

    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), RequestHandler)

    # Set engine on the server instance (matches start_http_server pattern)
    server.engine = engine
    # Auth + path allow-list, matching start_http_server.
    server.auth_token = TEST_TOKEN
    server.allow_dir = str(tmp_path)

    def serve():
        server.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    # Wait for server to start
    time.sleep(0.1)

    yield server, port, engine

    server.shutdown()


# The token the test server requires; helpers send it by default.
TEST_TOKEN = "test-token-123"


def _get(port, path, headers=None, token=TEST_TOKEN):
    """Make a GET request and return (status_code, body_dict)."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        req = urllib.request.Request(url)
        if token is not None:
            req.add_header("Authorization", f"Bearer {token}")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return resp.status, data
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _post(port, path, body=None, headers=None, token=TEST_TOKEN):
    """Make a POST request and return (status_code, body_dict)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body else b""
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if token is not None:
            req.add_header("Authorization", f"Bearer {token}")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class TestGetStatus:
    """Test GET /status endpoint."""

    def test_returns_200(self, test_server):
        _, port, _ = test_server
        status, body = _get(port, "/status")
        assert status == 200
        assert "is_recording" in body
        assert "is_transcribing" in body
        assert "model_loaded" in body
        assert "fsm" in body

    def test_returns_correct_initial_status(self, test_server):
        _, port, engine = test_server
        status, body = _get(port, "/status")
        assert status == 200
        assert body["is_recording"] is False
        assert body["is_transcribing"] is False


class TestGetConfig:
    """Test GET /config endpoint."""

    def test_returns_200(self, test_server):
        _, port, _ = test_server
        status, body = _get(port, "/config")
        assert status == 200

    def test_returns_config_dict(self, test_server):
        _, port, engine = test_server
        status, body = _get(port, "/config")
        assert status == 200
        assert body["model_size"] == "small"
        assert body["language"] == "fr"


class TestGetLastTranscription:
    """Test GET /last-transcription endpoint."""

    def test_returns_200(self, test_server):
        _, port, _ = test_server
        status, body = _get(port, "/last-transcription")
        assert status == 200

    def test_returns_text(self, test_server):
        _, port, engine = test_server
        engine.state.last_transcription = "hello world"
        status, body = _get(port, "/last-transcription")
        assert status == 200
        assert body["text"] == "hello world"

    def test_returns_none_when_no_transcription(self, test_server):
        _, port, engine = test_server
        engine.state.last_transcription = None
        status, body = _get(port, "/last-transcription")
        assert status == 200
        assert body["text"] is None


class TestPostConfig:
    """Test POST /config endpoint."""

    def test_updates_config(self, test_server):
        _, port, engine = test_server
        status, body = _post(port, "/config", {"model_size": "base"})
        assert status == 200
        assert body["status"] == "ok"
        assert engine.state.config["model_size"] == "base"

    def test_returns_new_config(self, test_server):
        _, port, engine = test_server
        status, body = _post(port, "/config", {"language": "fr"})
        assert status == 200
        assert body["config"]["language"] == "fr"

    def test_invalid_json_returns_400(self, test_server):
        _, port, _ = test_server
        url = f"http://127.0.0.1:{port}/config"
        req = urllib.request.Request(url, data=b"{invalid", method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {TEST_TOKEN}")
        try:
            urllib.request.urlopen(req, timeout=2)
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_empty_body_returns_ok(self, test_server):
        _, port, engine = test_server
        status, body = _post(port, "/config", {})
        assert status == 200


class TestPostStartStop:
    """Test POST /start and /stop endpoints."""

    def test_post_start(self, test_server):
        _, port, _ = test_server
        status, body = _post(port, "/start")
        assert status == 200
        assert body["status"] == "recording"

    def test_post_stop(self, test_server):
        _, port, _ = test_server
        status, body = _post(port, "/stop")
        assert status == 200
        assert body["status"] == "done"

    def test_post_stop_async(self, test_server):
        # Regression: /stop-async used to call engine.state._stop_event (wrong
        # attribute name), raising AttributeError -> 500 and never waking the
        # worker. It must return 200 and set the public stop_event.
        _, port, engine = test_server
        engine.state.stop_event.clear()
        status, body = _post(port, "/stop-async")
        assert status == 200
        assert body["status"] == "stopping"
        assert engine.state.stop_event.is_set()


class TestPostTranscribeFile:
    """Test POST /transcribe-file — the deterministic validation seam."""

    def test_transcribes_given_file(self, test_server, tmp_path):
        _, port, engine = test_server
        engine.transcribe_file = lambda path: "le test est fini"
        wav = tmp_path / "x.wav"  # inside the server's allow_dir (== tmp_path)
        status, body = _post(port, "/transcribe-file", {"path": str(wav)})
        assert status == 200
        assert body["text"] == "le test est fini"

    def test_missing_path_returns_400(self, test_server):
        _, port, _ = test_server
        status, body = _post(port, "/transcribe-file", {})
        assert status == 400
        assert "error" in body

    def test_model_not_loaded_returns_409(self, test_server, tmp_path):
        _, port, engine = test_server
        engine.transcribe_file = lambda path: None  # model unloaded / file missing
        status, body = _post(port, "/transcribe-file", {"path": str(tmp_path / "x.wav")})
        assert status == 409
        assert "error" in body

    def test_empty_transcription_is_200(self, test_server, tmp_path):
        # Silence transcribes to "" (ran, no speech) — must be 200, not 409.
        _, port, engine = test_server
        engine.transcribe_file = lambda path: ""
        status, body = _post(port, "/transcribe-file", {"path": str(tmp_path / "silence.wav")})
        assert status == 200
        assert body["text"] == ""

    def test_path_outside_allow_dir_returns_403(self, test_server):
        # Task 6.4: a path outside the allow-listed dir is rejected and never
        # opened/transcribed (arbitrary-read / existence-oracle defense).
        _, port, engine = test_server
        engine.transcribe_file = lambda path: pytest.fail("must not transcribe a disallowed path")
        status, body = _post(port, "/transcribe-file", {"path": "/etc/passwd"})
        assert status == 403
        assert "error" in body


class TestPostStreamFile:
    """Test POST /stream-file — the deterministic streaming validation seam."""

    def test_returns_ordered_chunk_texts(self, test_server, tmp_path):
        _, port, engine = test_server
        engine.stream_file = lambda path: ["alpha", "beta"]
        wav = tmp_path / "x.wav"
        status, body = _post(port, "/stream-file", {"path": str(wav)})
        assert status == 200
        assert body["texts"] == ["alpha", "beta"]
        assert body["text"] == "alpha beta"

    def test_missing_path_returns_400(self, test_server):
        _, port, _ = test_server
        status, body = _post(port, "/stream-file", {})
        assert status == 400

    def test_model_not_loaded_returns_409(self, test_server, tmp_path):
        _, port, engine = test_server
        engine.stream_file = lambda path: None
        status, body = _post(port, "/stream-file", {"path": str(tmp_path / "x.wav")})
        assert status == 409

    def test_no_chunks_is_200_empty(self, test_server, tmp_path):
        # Silence yields no chunks (ran, nothing usable) — 200 with empty list.
        _, port, engine = test_server
        engine.stream_file = lambda path: []
        status, body = _post(port, "/stream-file", {"path": str(tmp_path / "silence.wav")})
        assert status == 200
        assert body["texts"] == []
        assert body["text"] == ""

    def test_path_outside_allow_dir_returns_403(self, test_server):
        _, port, engine = test_server
        engine.stream_file = lambda path: pytest.fail("must not stream a disallowed path")
        status, body = _post(port, "/stream-file", {"path": "/etc/passwd"})
        assert status == 403


class TestApiSecurity:
    """Auth, DNS-rebinding, and body-size defenses on the control API."""

    def test_missing_token_returns_401(self, test_server):
        _, port, _ = test_server
        status, body = _get(port, "/status", token=None)
        assert status == 401
        assert "error" in body

    def test_wrong_token_returns_401(self, test_server):
        _, port, _ = test_server
        status, _ = _get(port, "/status", token="not-the-token")
        assert status == 401

    def test_valid_token_succeeds(self, test_server):
        _, port, _ = test_server
        status, _ = _get(port, "/status")  # default helper sends TEST_TOKEN
        assert status == 200

    def test_post_without_token_has_no_side_effect(self, test_server):
        _, port, engine = test_server
        called = []
        engine.start_recording = lambda: called.append(True)
        status, _ = _post(port, "/start", token=None)
        assert status == 401
        assert called == []  # the side effect never ran

    def test_foreign_host_returns_403(self, test_server):
        _, port, _ = test_server
        status, _ = _get(port, "/status", headers={"Host": "evil.example.com"})
        assert status == 403

    def test_origin_header_returns_403(self, test_server):
        # A browser fetch always attaches Origin; native clients never do.
        _, port, _ = test_server
        status, _ = _get(port, "/status", headers={"Origin": "https://evil.example.com"})
        assert status == 403

    def test_referer_header_returns_403(self, test_server):
        _, port, _ = test_server
        status, _ = _get(port, "/status", headers={"Referer": "https://evil.example.com/x"})
        assert status == 403

    def test_oversized_body_returns_413(self, test_server):
        # Declared Content-Length over the cap is rejected before the body is read.
        _, port, _ = test_server
        url = f"http://127.0.0.1:{port}/config"
        req = urllib.request.Request(url, data=b"{}", method="POST")
        req.add_header("Authorization", f"Bearer {TEST_TOKEN}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(64 * 1024 + 1))
        try:
            urllib.request.urlopen(req, timeout=2)
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 413


class TestUnknownEndpoints:
    """Test unknown endpoint handling."""

    def test_unknown_get_returns_404(self, test_server):
        _, port, _ = test_server
        status, body = _get(port, "/nonexistent")
        assert status == 404
        assert "error" in body

    def test_unknown_post_returns_404(self, test_server):
        _, port, _ = test_server
        status, body = _post(port, "/nonexistent")
        assert status == 404
        assert "error" in body


class TestSingleInstanceLock:
    """The :9090 bind is the single-instance lock: no port drift by default."""

    def _engine(self):
        return Engine(DictationState())

    def test_binds_free_port(self):
        from whispy.api.server import start_http_server

        port = _find_free_port()
        server = start_http_server(self._engine(), auth_token=TEST_TOKEN, start_port=port)
        try:
            assert server.server_address[1] == port
        finally:
            server.shutdown()

    def test_raises_when_port_busy_no_drift(self):
        # A second instance must fail fast on a busy port, NOT drift to port+1.
        from whispy.api.server import start_http_server

        port = _find_free_port()
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", port))
        holder.listen(1)
        try:
            with pytest.raises(OSError):
                start_http_server(self._engine(), auth_token=TEST_TOKEN, start_port=port)
        finally:
            holder.close()

    def test_harness_path_still_drifts(self):
        # The headless harness opts into drift (max_attempts>1) so it can run
        # beside a live daemon; verify it lands on the next free port.
        from whispy.api.server import start_http_server

        port = _find_free_port()
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", port))
        holder.listen(1)
        server = None
        try:
            server = start_http_server(
                self._engine(), auth_token=TEST_TOKEN, start_port=port, max_attempts=5
            )
            assert server.server_address[1] != port
        finally:
            holder.close()
            if server is not None:
                server.shutdown()

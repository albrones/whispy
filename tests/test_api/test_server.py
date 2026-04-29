"""Tests for the HTTP API server endpoints.

Uses a real HTTP server with a mock engine to test endpoint behavior.
"""

import json
import socket
import threading
import time
from http.server import HTTPServer
from unittest.mock import MagicMock

import pytest
import urllib.request
import urllib.error

from whispy.api.server import PORT, RequestHandler
from whispy.core.engine import DictationState, Engine


def _find_free_port():
    """Find a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def test_server(mocker):
    """Start a test HTTP server with a mock Engine."""
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

    def serve():
        server.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    # Wait for server to start
    time.sleep(0.1)

    yield server, port, engine

    server.shutdown()


def _get(port, path):
    """Make a GET request and return (status_code, body_dict)."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return resp.status, data
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _post(port, path, body=None):
    """Make a POST request and return (status_code, body_dict)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body else b""
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
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

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
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whispy.api.server import RequestHandler
from whispy.core.engine import DictationState, Engine
from whispy.core.segmentation import SENTENCE


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


class TestGetLevel:
    """GET /level: the live input level the Omarchy waveform pill polls."""

    def test_idle_level_is_zero(self, test_server, mocker):
        _, port, engine = test_server
        mocker.patch.object(engine, "get_level", return_value=0.7)
        status, body = _get(port, "/level")
        assert status == 200
        assert body == {"level": 0.0, "is_recording": False}

    def test_recording_level_is_clamped_to_one(self, test_server, mocker):
        _, port, engine = test_server
        engine.state.is_recording = True
        mocker.patch.object(engine, "get_level", return_value=1.8)
        status, body = _get(port, "/level")
        assert status == 200
        assert body == {"level": 1.0, "is_recording": True}

    def test_successful_poll_is_not_logged(self, test_server, capsys):
        _, port, _ = test_server
        _get(port, "/level")
        _get(port, "/status")
        out = capsys.readouterr().out
        assert "/status" in out
        assert "/level" not in out

    def test_requires_token(self, test_server):
        _, port, _ = test_server
        status, _ = _get(port, "/level", token=None)
        assert status == 401


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
        # Clipboard paste is the default delivery path: it hands the text over as
        # data, so accents and punctuation survive a non-US keyboard layout.
        assert body["copy_to_clipboard"] is True
        assert body["streaming_enabled"] is True


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
        status, body = _post(port, "/config", {"pause_ms": 800})
        assert status == 200
        assert body["status"] == "ok"
        assert engine.state.config["pause_ms"] == 800

    def test_returns_new_config(self, test_server):
        _, port, engine = test_server
        status, body = _post(port, "/config", {"copy_to_clipboard": True})
        assert status == 200
        assert body["config"]["copy_to_clipboard"] is True

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


class TestPostStopSyncViaWorker:
    """POST /stop delegates to Engine.stop_and_wait_for_transcription (fix-trigger-thread-blocking).

    Streaming is enabled by default (DEFAULT_CONFIG), so `test_server`'s engine
    is already wired for the streaming path.
    """

    def test_stop_returns_assembled_streaming_text(self, test_server, mocker, tmp_path):
        # Regression: /stop used to call run_transcription() directly, which
        # only knows the whole-file path — in streaming mode it always
        # returned None instead of the assembled chunk text.
        _, port, engine = test_server
        engine.state.model = MagicMock()
        mocker.patch.object(engine._audio_engine, "transcribe", side_effect=["hello", "world"])
        inject = mocker.patch.object(engine._text_injector, "inject")
        succeeded = mocker.patch.object(engine._notifier, "transcription_succeeded")

        engine.start_chunk_worker()
        engine.start_transcription_worker()
        try:
            status, _ = _post(port, "/start")
            assert status == 200

            for name in ("c1.wav", "c2.wav"):
                chunk = tmp_path / name
                chunk.write_bytes(b"\x00" * 100)
                engine._enqueue_chunk(str(chunk), SENTENCE)
            engine._chunk_queue.join()

            status, body = _post(port, "/stop")
            assert status == 200
            assert body["status"] == "done"
            assert body["text"] == "hello world"
            inject.assert_called_once_with("hello world")
            succeeded.assert_called_once()
        finally:
            engine.stop_transcription_worker()
            engine.stop_chunk_worker()

    def test_stop_while_not_recording_is_noop(self, test_server, mocker):
        _, port, engine = test_server
        succeeded = mocker.patch.object(engine._notifier, "transcription_succeeded")

        status, body = _post(port, "/stop")

        assert status == 200
        assert body == {"status": "done", "text": None}
        succeeded.assert_not_called()

    def test_stop_fires_success_cue_exactly_once_non_streaming(self, test_server, mocker, tmp_path):
        _, port, engine = test_server
        engine.update_config({"streaming_enabled": False})
        engine.state.model = MagicMock()
        wav = tmp_path / "rec.wav"
        wav.write_bytes(b"\x00" * 6000)
        mocker.patch.object(type(engine._audio_engine), "recording_path", property(lambda self: str(wav)))
        mocker.patch.object(engine._audio_engine, "transcribe", return_value="hello")
        mocker.patch.object(engine._text_injector, "inject")
        succeeded = mocker.patch.object(engine._notifier, "transcription_succeeded")

        engine.start_transcription_worker()
        try:
            status, _ = _post(port, "/start")
            assert status == 200

            status, body = _post(port, "/stop")
            assert status == 200
            assert body["status"] == "done"
            succeeded.assert_called_once()
        finally:
            engine.stop_transcription_worker()


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


class TestFailClosedAuth:
    """No configured token (None or "") SHALL reject every endpoint with 401 (harden-privacy-file-perms)."""

    def _server_with_token(self, mocker, tmp_path, token):
        import whispy.core.audio as audio_module

        recording_file = tmp_path / "whispy.wav"
        recording_file.write_bytes(b"\x00" * 6000)
        mocker.patch.object(audio_module, "RECORDING_PATH", str(recording_file))

        ds = DictationState()
        engine = Engine(ds)
        mock_popen = mocker.patch("subprocess.Popen")
        mock_instance = MagicMock()
        mock_instance.poll.return_value = None
        mock_popen.return_value = mock_instance

        port = _find_free_port()
        server = HTTPServer(("127.0.0.1", port), RequestHandler)
        server.engine = engine
        server.auth_token = token
        server.allow_dir = str(tmp_path)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)
        return server, port

    @pytest.mark.parametrize("token", [None, ""])
    def test_every_endpoint_rejected_when_no_token_configured(self, mocker, tmp_path, token):
        server, port = self._server_with_token(mocker, tmp_path, token)
        try:
            for path in ("/status", "/config"):
                status, body = _get(port, path, token=None)
                assert status == 401, f"GET {path} should be 401 when no token configured"
                assert "error" in body

            for path in ("/start", "/stop"):
                status, body = _post(port, path, token=None)
                assert status == 401, f"POST {path} should be 401 when no token configured"
                assert "error" in body
        finally:
            server.shutdown()

    @pytest.mark.parametrize("token", [None, ""])
    def test_rejected_even_with_correct_host_and_no_origin(self, mocker, tmp_path, token):
        # Correct Host, no Origin/Referer — would pass the DNS-rebinding and
        # browser-origin checks; the missing token must still fail closed.
        server, port = self._server_with_token(mocker, tmp_path, token)
        try:
            status, body = _get(
                port,
                "/status",
                headers={"Host": f"127.0.0.1:{port}"},
                token=None,
            )
            assert status == 401
            assert "error" in body
        finally:
            server.shutdown()


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
            server = start_http_server(self._engine(), auth_token=TEST_TOKEN, start_port=port, max_attempts=5)
            assert server.server_address[1] != port
        finally:
            holder.close()
            if server is not None:
                server.shutdown()


def _wav_bytes(rate=16_000, channels=1, seconds=0.5):
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * channels * int(rate * seconds))
    return buffer.getvalue()


def _post_raw(port, path, data, content_type="audio/wav", headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("Authorization", f"Bearer {TEST_TOKEN}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class TestPostTranscribe:
    """POST /transcribe — raw WAV upload, the Régie client's contract."""

    def _with_model(self, engine, mocker, text="bonjour à tous"):
        engine.state.model = object()
        seen = {}

        def _transcribe(path):
            seen["path"] = path
            seen["bytes"] = Path(path).read_bytes()
            return text

        engine.transcribe_file = _transcribe
        inject = mocker.patch.object(engine._text_injector, "inject")
        return seen, inject

    def test_wav_is_transcribed_without_injection_and_not_kept(self, test_server, mocker):
        _, port, engine = test_server
        seen, inject = self._with_model(engine, mocker)
        wav = _wav_bytes()
        status, body = _post_raw(port, "/transcribe", wav)
        assert (status, body) == (200, {"text": "bonjour à tous"})
        assert seen["bytes"] == wav
        assert not Path(seen["path"]).exists()
        inject.assert_not_called()

    def test_non_wav_body_is_400_naming_the_expected_format(self, test_server, mocker):
        _, port, engine = test_server
        self._with_model(engine, mocker)
        status, body = _post_raw(port, "/transcribe", b"not audio at all")
        assert status == 400
        assert "16 kHz mono" in body["error"]

    def test_wrong_content_type_is_400(self, test_server, mocker):
        _, port, engine = test_server
        self._with_model(engine, mocker)
        status, body = _post_raw(port, "/transcribe", _wav_bytes(), content_type="application/json")
        assert status == 400
        assert "audio/wav" in body["error"]

    def test_wrong_sample_rate_is_400(self, test_server, mocker):
        _, port, engine = test_server
        self._with_model(engine, mocker)
        status, body = _post_raw(port, "/transcribe", _wav_bytes(rate=44_100, channels=2))
        assert status == 400
        assert "44100 Hz" in body["error"]

    def test_oversized_body_is_413_before_reading(self, test_server, mocker):
        import http.client

        from whispy.api.server import MAX_AUDIO_BODY_BYTES

        _, port, engine = test_server
        self._with_model(engine, mocker)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.putrequest("POST", "/transcribe")
        conn.putheader("Content-Type", "audio/wav")
        conn.putheader("Authorization", f"Bearer {TEST_TOKEN}")
        conn.putheader("Content-Length", str(MAX_AUDIO_BODY_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        assert response.status == 413
        assert "error" in json.loads(response.read())

    def test_model_not_loaded_is_503(self, test_server):
        _, port, engine = test_server
        engine.state.model = None
        status, body = _post_raw(port, "/transcribe", _wav_bytes())
        assert status == 503
        assert "error" in body

    def test_requires_the_token(self, test_server):
        _, port, _ = test_server
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/transcribe",
            data=b"RIFF",  # tiny: the auth gate answers before reading the body
            method="POST",
            headers={"Content-Type": "audio/wav"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=2)
        assert exc.value.code == 401

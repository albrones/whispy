#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

WHISPER_CLI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "whisper.cpp",
    "build",
    "bin",
    "whisper-cli",
)
WHISPER_MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "whisper.cpp",
    "models",
    "ggml-base.bin",
)
RECORDING_PATH = os.path.join(tempfile.gettempdir(), "whisper-dictation.wav")
PORT = 9090


class DictationState:
    def __init__(self):
        self.recording_process = None
        self.is_recording = False
        self.lock = threading.Lock()


state = DictationState()


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
        return True


def stop_recording_and_transcribe():
    with state.lock:
        if not state.is_recording:
            return None
        state.is_recording = False

    proc = state.recording_process
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    if not os.path.exists(RECORDING_PATH):
        return None

    text = transcribe(RECORDING_PATH)
    try:
        os.remove(RECORDING_PATH)
    except OSError:
        pass
    if text:
        type_text(text)
    return text


def transcribe(audio_path):
    try:
        result = subprocess.run(
            [
                WHISPER_CLI,
                "-m",
                WHISPER_MODEL,
                "-l",
                "fr",
                "-nt",
                "-np",
                "-f",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = result.stdout.strip()
        if not text:
            return None
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return " ".join(lines)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"Transcription error: {e}", file=sys.stderr)
        return None


def type_text(text):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'tell application "System Events" to keystroke "{escaped}"',
        ],
        timeout=5,
    )


def play_sound(sound_name):
    subprocess.run(
        ["afplay", f"/System/Library/Sounds/{sound_name}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "recording": state.is_recording,
                    }
                ).encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/start":
            play_sound("Tink.aiff")
            start_recording()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "recording"}).encode())

        elif self.path == "/stop":
            text = stop_recording_and_transcribe()
            play_sound("Pop.aiff")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "status": "done",
                        "text": text,
                    }
                ).encode()
            )

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[dictation] {format % args}")


def main():
    if not os.path.isfile(WHISPER_MODEL):
        print(f"Error: Whisper model not found at {WHISPER_MODEL}", file=sys.stderr)
        print(
            "Run: cd whisper.cpp/models && bash download-ggml-model.sh base",
            file=sys.stderr,
        )
        sys.exit(1)
    if not os.path.isfile(WHISPER_CLI):
        print(f"Error: whisper-cli not found at {WHISPER_CLI}", file=sys.stderr)
        print(
            "Build whisper.cpp first: cd whisper.cpp && mkdir build && cd build && cmake .. && make",
            file=sys.stderr,
        )
        sys.exit(1)
    server = HTTPServer(("127.0.0.1", PORT), RequestHandler)
    print(f"Whisper dictation daemon running on port {PORT}")
    signal.signal(signal.SIGTERM, lambda *_: server.shutdown())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    print("Daemon stopped.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from faster_whisper import WhisperModel

WHISPER_MODEL_SIZE = "small"
WHISPER_MODEL = None
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
        segments, info = WHISPER_MODEL.transcribe(
            audio_path,
            language="fr",
            beam_size=1,
            best_of=2,
        )
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())
        text = " ".join(text_parts)
        if not text:
            return None
        return text
    except Exception as e:
        print(f"Transcription error: {e}", file=sys.stderr)
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
    global WHISPER_MODEL
    try:
        print(f"Loading faster-whisper model '{WHISPER_MODEL_SIZE}'...")
        WHISPER_MODEL = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",
        )
        print(f"Model loaded successfully")
    except Exception as e:
        print(f"Error loading Whisper model: {e}", file=sys.stderr)
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

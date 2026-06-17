"""Environment diagnostic for Whispy.

Run via ``python whispy_daemon.py --doctor`` (or ``make doctor``). Checks the
things that most often block a fresh install — the audio backend, the Whisper
model, the platform permissions/prerequisites, and whether the daemon is
already running — and prints an actionable report.

Each check is a small function returning a :class:`CheckResult`, so the report
logic can be unit-tested with injected checks.
"""

from __future__ import annotations

import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .core.config import DEFAULT_CONFIG, get_default_config_path, load_config

OK = "ok"
WARN = "warn"
FAIL = "fail"

_SYMBOLS = {OK: "✓", WARN: "!", FAIL: "✗"}


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""

    name: str
    status: str
    detail: str


def check_audio_backend() -> CheckResult:
    """sounddevice (PortAudio) is required for cross-platform audio capture."""
    try:
        import sounddevice  # noqa: F401
    except Exception as exc:
        return CheckResult(
            "audio backend",
            FAIL,
            f"sounddevice unavailable ({exc}) — `pip install sounddevice` and ensure PortAudio is present",
        )
    return CheckResult("audio backend", OK, "sounddevice (PortAudio) available")


def check_xdotool() -> CheckResult:
    """On Linux/X11, xdotool is required for text injection."""
    if sys.platform != "linux":
        return CheckResult("xdotool", OK, "not required on this platform")
    path = shutil.which("xdotool")
    if path:
        return CheckResult("xdotool", OK, path)
    return CheckResult("xdotool", FAIL, "not found — install with your package manager (e.g. `apt install xdotool`)")


def check_model(config_path: Path | None = None) -> CheckResult:
    """The configured Whisper model should be present in the HF cache."""
    try:
        cfg = load_config(config_path or get_default_config_path())
    except Exception:
        cfg = dict(DEFAULT_CONFIG)
    size = cfg.get("model_size", DEFAULT_CONFIG["model_size"])

    cache = Path.home() / ".cache" / "huggingface" / "hub"
    if cache.exists() and list(cache.glob(f"*faster-whisper-{size}*")):
        return CheckResult("model", OK, f"{size} cached")
    return CheckResult("model", WARN, f"{size} not downloaded yet (downloads automatically on first use)")


def check_input_monitoring() -> CheckResult:
    """Input Monitoring is required for the Fn-key event tap."""
    try:
        from Quartz import CGPreflightListenEventAccess
    except Exception:
        return CheckResult("Input Monitoring", WARN, "cannot verify (Quartz unavailable)")
    if CGPreflightListenEventAccess():
        return CheckResult("Input Monitoring", OK, "granted")
    return CheckResult(
        "Input Monitoring",
        FAIL,
        "not granted — System Settings → Privacy & Security → Input Monitoring",
    )


def check_accessibility() -> CheckResult:
    """Accessibility is required for osascript text injection."""
    try:
        from ApplicationServices import AXIsProcessTrusted
    except Exception:
        return CheckResult(
            "Accessibility",
            WARN,
            "cannot verify — check System Settings → Privacy & Security → Accessibility",
        )
    if AXIsProcessTrusted():
        return CheckResult("Accessibility", OK, "granted")
    return CheckResult(
        "Accessibility",
        FAIL,
        "not granted — System Settings → Privacy & Security → Accessibility",
    )


def check_microphone() -> CheckResult:
    """Microphone access is required to record audio."""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
    except Exception:
        return CheckResult(
            "Microphone",
            WARN,
            "cannot verify — check System Settings → Privacy & Security → Microphone",
        )
    # 3 = authorized, 0 = not determined, 1/2 = restricted/denied
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
    if status == 3:
        return CheckResult("Microphone", OK, "granted")
    if status == 0:
        return CheckResult("Microphone", WARN, "not yet requested (granted on first recording)")
    return CheckResult("Microphone", FAIL, "denied — System Settings → Privacy & Security → Microphone")


def check_daemon(port: int = 9090) -> CheckResult:
    """The daemon exposes an HTTP status endpoint when running."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2):
            return CheckResult("Daemon", OK, f"running on :{port}")
    except (urllib.error.URLError, OSError):
        return CheckResult("Daemon", WARN, "not running (start with ./install.sh)")


CHECKS = [
    check_audio_backend,
    check_xdotool,
    check_model,
    check_input_monitoring,
    check_accessibility,
    check_microphone,
    check_daemon,
]


def run_doctor(checks=None) -> int:
    """Run all checks, print a report, and return a process exit code.

    Returns 0 when no check failed, 1 when at least one blocking check failed.
    """
    checks = checks if checks is not None else CHECKS
    results = [check() for check in checks]

    print("Whispy doctor — environment diagnostic\n")
    for r in results:
        print(f"  [{_SYMBOLS.get(r.status, '?')}] {r.name}: {r.detail}")

    failed = [r for r in results if r.status == FAIL]
    print()
    if failed:
        print(f"{len(failed)} blocking issue(s) found — see above.")
        return 1
    print("All critical checks passed.")
    return 0

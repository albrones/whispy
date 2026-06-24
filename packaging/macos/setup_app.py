"""py2app build spec for Whispy.app (native macOS menu-bar bundle).

Bundles its OWN Python interpreter + all deps inside Whispy.app, so the macOS
microphone / Accessibility / Input-Monitoring grants attach to a stable
"Whispy" identity and survive Homebrew/python.org interpreter upgrades — unlike
the bare `python3 whispy_daemon.py` LaunchAgent, whose grant breaks whenever the
interpreter path changes (the 3.13 -> 3.14 breakage that motivated this).

Run from the REPO ROOT (paths below are repo-relative):
    .venv/bin/python packaging/macos/setup_app.py py2app
Or via packaging/macos/build_app.sh (which also ad-hoc code-signs the result).
"""

from setuptools import setup

# Version mirrors pyproject.toml [project].version.
VERSION = "0.1.0"

APP = ["whispy_daemon.py"]

# Menu bar uses a unicode glyph at runtime (icon=None in ui/menu_bar.py), so the
# PNG isn't strictly required live; bundle it anyway for any future icon use.
DATA_FILES = [("icons", ["icons/whispy.png"])]

PLIST = {
    "CFBundleName": "Whispy",
    "CFBundleDisplayName": "Whispy",
    "CFBundleIdentifier": "com.whispy",
    "CFBundleVersion": VERSION,
    "CFBundleShortVersionString": VERSION,
    # Menu-bar / agent app: no Dock icon, no main window.
    "LSUIElement": True,
    "LSMinimumSystemVersion": "12.0",
    # TCC usage strings — REQUIRED for the OS to show a permission prompt instead
    # of silently denying. Their absence on the bare interpreter is exactly why
    # the LaunchAgent path could never (re)acquire the microphone.
    "NSMicrophoneUsageDescription": "Whispy records your voice to transcribe speech to text.",
    "NSAppleEventsUsageDescription": "Whispy types transcribed text into the focused app via osascript.",
    "NSInputMonitoringUsageDescription": "Whispy watches the push-to-talk hotkey to start and stop dictation.",
}

OPTIONS = {
    "iconfile": "packaging/macos/whispy.icns",
    "plist": PLIST,
    # argv emulation pulls in Carbon and is unneeded for a menu-bar daemon.
    "argv_emulation": False,
    "optimize": 1,
    # Whole packages copied verbatim so their native libs (.dylib/.so) and lazily
    # imported submodules (platform adapters import concretes inside closures, so
    # py2app's static scan misses them) are all present in the bundle.
    "packages": [
        "whispy",
        "faster_whisper",
        "ctranslate2",
        "tokenizers",
        "onnxruntime",
        "av",
        "sounddevice",
        # The PyPI sounddevice wheel loads its PortAudio dylib at runtime from
        # this data package (_sounddevice_data/portaudio-binaries/
        # libportaudio.dylib). modulegraph can't see that ctypes/cffi load, so
        # the whole package must be force-included or `import sounddevice` fails
        # in the bundle (sd is None -> no capture at all).
        "_sounddevice_data",
        "cffi",
        "huggingface_hub",
        # certifi ships its CA bundle (cacert.pem) as package data; needed so
        # SSL_CERT_FILE points at a real file for any HTTPS model download.
        "certifi",
        "rumps",
    ],
    "includes": [
        "_cffi_backend",
        "objc",
        "Quartz",
        "AVFoundation",
        "ApplicationServices",
        "AppKit",
        "Foundation",
        "CoreFoundation",
    ],
    # Build-time / other-platform / test deps that must not bloat the bundle.
    "excludes": [
        "pynput",
        "pystray",
        "PIL",
        "py2app",
        "pytest",
        "tkinter",
    ],
}

setup(
    name="Whispy",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

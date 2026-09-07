"""Configuration management for Whispy.

Handles loading, saving, validation, and migration of the user config file.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Curated push-to-talk trigger presets for the menu UI: ordered (label, value)
# where value is None for the platform default (Fn on macOS) or a macOS keycode
# (int). Keycodes are Carbon virtual keycodes (what CGEvent reports). Only keys
# that work as a *hold* without blocking typing or stealing system shortcuts
# are listed — letter/space/Esc keys and the Caps Lock toggle are deliberately
# out, and so are modifier combinations: the macOS event tap is listen-only and
# cannot consume the event, so any combination the focused application also
# binds would fire that application's own shortcut on both the start and the
# stop press.
#
# A modifier-combination string (e.g. "ctrl+alt+cmd+e", see
# hardware/event_decode.parse_trigger) is still a valid hand-edited config
# value and is honoured by the listener; it just has no preset item here.
TRIGGER_PRESETS: list[tuple[str, int | str | None]] = [
    ("Fn", None),  # platform default; None keeps "default" semantics (keycode 63)
    ("Right Command", 54),
    ("Right Option", 61),
    ("F13", 105),
]

# Default configuration values
DEFAULT_CONFIG: dict[str, Any] = {
    "copy_to_clipboard": False,
    # Register the app as a macOS login item (start at login). macOS .app
    # bundle only; ignored on the loose-script path (LaunchAgent handles it).
    "start_at_login": False,
    "min_recording_duration": 0.3,
    # User-curated terms (names, jargon) used to bias transcription toward the
    # words the user habitually says. Empty by default.
    "custom_vocabulary": [],
    # Push-to-talk trigger key/combo. ``None`` means "use the platform default"
    # (Fn / keycode 63 on macOS, Right Ctrl on Linux), resolved at runtime by
    # the engine. May be an int (macOS keycode) or a string (key/combo name).
    "trigger": None,
    # How the trigger controls recording. "hold" is push-to-talk — the trigger
    # must be held for the whole dictation (current, default behavior).
    # "toggle" means a trigger press starts recording and the next trigger
    # press stops it; the trigger release does not stop recording. This is
    # deliberately a key of its own rather than a property of each trigger
    # preset, so any trigger composes with either mode without doubling the
    # menu's trigger list.
    "trigger_mode": "hold",
    # --- Streaming / incremental transcription ---
    # When enabled (default), the recording is segmented on silence (and a max
    # length) and each chunk is transcribed during recording, so the assembled
    # text is typed near-instantly on release instead of after a multi-second
    # whole-file pass. Disable to use the legacy record-then-transcribe path.
    "streaming_enabled": True,
    # Minimum trailing silence (milliseconds) that closes a chunk.
    "pause_ms": 600,
    # Minimum *voiced* seconds a chunk must hold before a pause may close it.
    # Each chunk is one independent model call, and a chunk carrying too little
    # speech is resolved into the wrong language (an isolated "oui" of 0.39s
    # voiced came back as English 5/5; the same word with 0.72s voiced was
    # correct 5/5). Below this the segmenter keeps buffering, so the short word
    # rides along with its neighbour. Provisional: both measurements come from
    # synthesized speech with a single voice, so a real microphone or room may
    # move where VAD counts a frame as voiced -- retune rather than refile.
    # Distinct from min_chunk_s below, which discards; this one only defers.
    "min_speech_s": 0.7,
    # A chunk shorter than this (seconds) is discarded rather than transcribed
    # (mirrors min_recording_duration, applied per chunk).
    "min_chunk_s": 0.4,
    # Hard cap (seconds) on chunk length: force-flush run-on speech with no pause
    # so streaming keeps making progress and never builds one huge packet.
    "max_chunk_s": 12.0,
    # WebRTC VAD aggressiveness (0-3): higher = more aggressive at classifying
    # audio as non-speech. Used to find chunk boundaries (gain-independent).
    "vad_aggressiveness": 2,
}

# Config version for migration tracking
CONFIG_VERSION = 1


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize config values. Returns a cleaned copy with only known keys."""
    # Start fresh with defaults — discard any unknown keys from input
    validated = dict(DEFAULT_CONFIG)

    # Merge known keys from config
    for key in DEFAULT_CONFIG:
        if key in config:
            validated[key] = config[key]

    # Preserve _version for migration tracking
    if "_version" in config:
        validated["_version"] = config["_version"]

    # Validate copy_to_clipboard (must be bool)
    ctc = validated.get("copy_to_clipboard")
    if not isinstance(ctc, bool):
        print(
            f"[config] Invalid copy_to_clipboard '{ctc}', defaulting to {DEFAULT_CONFIG['copy_to_clipboard']}",
            file=sys.stderr,
        )
        validated["copy_to_clipboard"] = DEFAULT_CONFIG["copy_to_clipboard"]

    # Validate start_at_login (must be bool)
    sal = validated.get("start_at_login")
    if not isinstance(sal, bool):
        print(
            f"[config] Invalid start_at_login '{sal}', defaulting to {DEFAULT_CONFIG['start_at_login']}",
            file=sys.stderr,
        )
        validated["start_at_login"] = DEFAULT_CONFIG["start_at_login"]

    # Validate min_recording_duration (must be a non-negative number)
    mrd = validated.get("min_recording_duration")
    if not isinstance(mrd, int | float) or isinstance(mrd, bool) or mrd < 0:
        print(
            f"[config] Invalid min_recording_duration '{mrd}', defaulting to {DEFAULT_CONFIG['min_recording_duration']}",
            file=sys.stderr,
        )
        validated["min_recording_duration"] = DEFAULT_CONFIG["min_recording_duration"]

    # Validate trigger (None = platform default, else a positive int keycode or
    # a non-empty key/combo string).
    trigger = validated.get("trigger")
    trigger_ok = (
        trigger is None
        or (isinstance(trigger, int) and not isinstance(trigger, bool) and trigger >= 0)
        or (isinstance(trigger, str) and trigger.strip() != "")
    )
    if not trigger_ok:
        print(
            f"[config] Invalid trigger '{trigger}', defaulting to platform default (None)",
            file=sys.stderr,
        )
        validated["trigger"] = DEFAULT_CONFIG["trigger"]
    elif isinstance(trigger, str):
        validated["trigger"] = trigger.strip()

    # Validate trigger_mode (must be exactly "hold" or "toggle").
    trigger_mode = validated.get("trigger_mode")
    if trigger_mode not in ("hold", "toggle"):
        print(
            f"[config] Invalid trigger_mode '{trigger_mode}', defaulting to {DEFAULT_CONFIG['trigger_mode']}",
            file=sys.stderr,
        )
        validated["trigger_mode"] = DEFAULT_CONFIG["trigger_mode"]

    # Validate streaming_enabled (must be bool).
    se = validated.get("streaming_enabled")
    if not isinstance(se, bool):
        print(
            f"[config] Invalid streaming_enabled '{se}', defaulting to {DEFAULT_CONFIG['streaming_enabled']}",
            file=sys.stderr,
        )
        validated["streaming_enabled"] = DEFAULT_CONFIG["streaming_enabled"]

    # Validate pause_ms (must be a positive number; bool rejected).
    pause = validated.get("pause_ms")
    if not isinstance(pause, int | float) or isinstance(pause, bool) or pause <= 0:
        print(
            f"[config] Invalid pause_ms '{pause}', defaulting to {DEFAULT_CONFIG['pause_ms']}",
            file=sys.stderr,
        )
        validated["pause_ms"] = DEFAULT_CONFIG["pause_ms"]

    # Validate min_speech_s (must be a non-negative number; bool rejected).
    mss = validated.get("min_speech_s")
    if not isinstance(mss, int | float) or isinstance(mss, bool) or mss < 0:
        print(
            f"[config] Invalid min_speech_s '{mss}', defaulting to {DEFAULT_CONFIG['min_speech_s']}",
            file=sys.stderr,
        )
        validated["min_speech_s"] = DEFAULT_CONFIG["min_speech_s"]

    # Validate min_chunk_s (must be a non-negative number; bool rejected).
    mcs = validated.get("min_chunk_s")
    if not isinstance(mcs, int | float) or isinstance(mcs, bool) or mcs < 0:
        print(
            f"[config] Invalid min_chunk_s '{mcs}', defaulting to {DEFAULT_CONFIG['min_chunk_s']}",
            file=sys.stderr,
        )
        validated["min_chunk_s"] = DEFAULT_CONFIG["min_chunk_s"]

    # Validate max_chunk_s (must be a positive number greater than min_chunk_s).
    maxcs = validated.get("max_chunk_s")
    if not isinstance(maxcs, int | float) or isinstance(maxcs, bool) or maxcs <= validated["min_chunk_s"]:
        print(
            f"[config] Invalid max_chunk_s '{maxcs}', defaulting to {DEFAULT_CONFIG['max_chunk_s']}",
            file=sys.stderr,
        )
        validated["max_chunk_s"] = DEFAULT_CONFIG["max_chunk_s"]

    # Validate vad_aggressiveness (integer 0-3; bool rejected).
    va = validated.get("vad_aggressiveness")
    if not isinstance(va, int) or isinstance(va, bool) or va < 0 or va > 3:
        print(
            f"[config] Invalid vad_aggressiveness '{va}', defaulting to {DEFAULT_CONFIG['vad_aggressiveness']}",
            file=sys.stderr,
        )
        validated["vad_aggressiveness"] = DEFAULT_CONFIG["vad_aggressiveness"]

    # Validate custom_vocabulary (must be a list of non-empty strings).
    vocab = validated.get("custom_vocabulary")
    if not isinstance(vocab, list):
        if vocab is not None:
            print(
                f"[config] Invalid custom_vocabulary '{vocab}', defaulting to []",
                file=sys.stderr,
            )
        validated["custom_vocabulary"] = []
    else:
        cleaned = [term.strip() for term in vocab if isinstance(term, str) and term.strip()]
        validated["custom_vocabulary"] = cleaned

    return validated


def _migrate_config(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    """Migrate config from older versions to the current version.

    Adds any missing keys with defaults, and handles known migration paths.
    """
    migrated = dict(config)

    # No version-specific step remains: the only one (v0 -> v1) added
    # auto_detect_min_duration, a key the Parakeet backend no longer has.
    # Filling in missing defaults below covers every version.

    # Add any missing default keys
    for key, value in DEFAULT_CONFIG.items():
        if key not in migrated:
            migrated[key] = value

    # Set current version
    migrated["_version"] = CONFIG_VERSION

    # Save the migrated config
    save_config(migrated, config_path)

    return migrated


def load_config(config_path: Path) -> dict[str, Any]:
    """Load config from disk, falling back to defaults.

    Args:
        config_path: Path to the JSON config file.

    Returns:
        Validated and migrated config dict.
    """
    config = dict(DEFAULT_CONFIG)
    file_loaded = False

    if config_path.exists():
        try:
            with open(config_path) as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                config.update(saved)
                file_loaded = True
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[config] Failed to load {config_path}: {exc}", file=sys.stderr)
            # Corrupted file: return defaults without migration

    # Validate
    config = _validate_config(config)

    # Migrate only if the file was successfully loaded
    if file_loaded:
        config = _migrate_config(config, config_path)

    return config


def save_config(config: dict[str, Any], config_path: Path) -> None:
    """Persist config to disk atomically, filtering to known keys.

    Args:
        config: Config dict to save.
        config_path: Path to write to.
    """
    filtered: dict[str, Any] = {}
    for key in DEFAULT_CONFIG:
        if key in config:
            filtered[key] = config[key]
        else:
            filtered[key] = DEFAULT_CONFIG[key]

    # Preserve _version key for migration tracking
    if "_version" in config:
        filtered["_version"] = config["_version"]

    config_dir = config_path.parent
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        try:
            config_dir.chmod(0o700)
        except OSError as exc:
            print(f"[config] Failed to set permissions on {config_dir}: {exc}", file=sys.stderr)
        tmp_path = config_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(filtered, f, indent=2)
        try:
            tmp_path.chmod(0o600)
        except OSError as exc:
            print(f"[config] Failed to set permissions on {tmp_path}: {exc}", file=sys.stderr)
        os.replace(tmp_path, config_path)
    except OSError as exc:
        print(f"[config] Failed to save {config_path}: {exc}", file=sys.stderr)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def get_default_config_path() -> Path:
    """Return the default config file path."""
    return Path.home() / ".config" / "whispy" / "config.json"

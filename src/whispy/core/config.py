"""Configuration management for Whispy.

Handles loading, saving, validation, and migration of the user config file.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Valid model sizes for faster-whisper
VALID_MODEL_SIZES: List[str] = ["tiny", "base", "small", "medium", "large-v3"]

# Supported languages with display names
SUPPORTED_LANGUAGES: Dict[str, str] = {
    "fr": "French",
    "en": "English",
}

# Model presets for UI display
MODEL_PRESETS: Dict[str, Dict[str, str]] = {
    "tiny": {
        "label": "Fast (tiny)",
        "description": "75 MB — fastest, limited quality",
    },
    "base": {
        "label": "Light (base)",
        "description": "142 MB — good speed/quality balance",
    },
    "small": {"label": "Normal (small)", "description": "466 MB — recommended"},
    "medium": {"label": "Accurate (medium)", "description": "1.5 GB — best quality"},
    "large-v3": {
        "label": "Maximum (large)",
        "description": "2.9 GB — maximum quality, slow",
    },
}

# Default configuration values
DEFAULT_CONFIG: Dict[str, Any] = {
    "model_size": "small",
    "language": "fr",
    "beam_size": 1,
    "best_of": 2,
    "copy_to_clipboard": False,
    "auto_detect_min_duration": 0.5,
}

# Config version for migration tracking
CONFIG_VERSION = 1


def _validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
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

    # Validate model_size
    if validated.get("model_size") not in VALID_MODEL_SIZES:
        print(
            f"[config] Invalid model_size '{validated.get('model_size')}', "
            f"defaulting to '{DEFAULT_CONFIG['model_size']}'",
            file=sys.stderr,
        )
        validated["model_size"] = DEFAULT_CONFIG["model_size"]

    # Validate language
    if validated.get("language") not in SUPPORTED_LANGUAGES:
        print(
            f"[config] Invalid language '{validated.get('language')}', "
            f"defaulting to '{DEFAULT_CONFIG['language']}'",
            file=sys.stderr,
        )
        validated["language"] = DEFAULT_CONFIG["language"]

    # Validate beam_size (must be positive int)
    beam = validated.get("beam_size")
    if not isinstance(beam, int) or beam < 1:
        print(
            f"[config] Invalid beam_size '{beam}', defaulting to {DEFAULT_CONFIG['beam_size']}",
            file=sys.stderr,
        )
        validated["beam_size"] = DEFAULT_CONFIG["beam_size"]

    # Validate best_of (must be positive int)
    best = validated.get("best_of")
    if not isinstance(best, int) or best < 1:
        print(
            f"[config] Invalid best_of '{best}', defaulting to {DEFAULT_CONFIG['best_of']}",
            file=sys.stderr,
        )
        validated["best_of"] = DEFAULT_CONFIG["best_of"]

    # Validate copy_to_clipboard (must be bool)
    ctc = validated.get("copy_to_clipboard")
    if not isinstance(ctc, bool):
        print(
            f"[config] Invalid copy_to_clipboard '{ctc}', defaulting to {DEFAULT_CONFIG['copy_to_clipboard']}",
            file=sys.stderr,
        )
        validated["copy_to_clipboard"] = DEFAULT_CONFIG["copy_to_clipboard"]

    # Validate auto_detect_min_duration (must be positive number)
    adm = validated.get("auto_detect_min_duration")
    if not isinstance(adm, (int, float)) or adm < 0:
        print(
            f"[config] Invalid auto_detect_min_duration '{adm}', defaulting to {DEFAULT_CONFIG['auto_detect_min_duration']}",
            file=sys.stderr,
        )
        validated["auto_detect_min_duration"] = DEFAULT_CONFIG["auto_detect_min_duration"]

    return validated


def _migrate_config(config: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    """Migrate config from older versions to the current version.

    Adds any missing keys with defaults, and handles known migration paths.
    """
    migrated = dict(config)
    version = migrated.get("_version", 0)

    if version == 0:
        # From v0 to v1: add auto_detect_min_duration if missing
        if "auto_detect_min_duration" not in migrated:
            migrated["auto_detect_min_duration"] = DEFAULT_CONFIG["auto_detect_min_duration"]

    # Add any missing default keys
    for key, value in DEFAULT_CONFIG.items():
        if key not in migrated:
            migrated[key] = value

    # Set current version
    migrated["_version"] = CONFIG_VERSION

    # Save the migrated config
    save_config(migrated, config_path)

    return migrated


def load_config(config_path: Path) -> Dict[str, Any]:
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


def save_config(config: Dict[str, Any], config_path: Path) -> None:
    """Persist config to disk atomically, filtering to known keys.

    Args:
        config: Config dict to save.
        config_path: Path to write to.
    """
    filtered: Dict[str, Any] = {}
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
        tmp_path = config_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(filtered, f, indent=2)
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

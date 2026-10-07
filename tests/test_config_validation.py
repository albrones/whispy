"""Tests for config validation in save_config and restart path resolution."""

import json
import logging
import os
import shutil
import stat
import sys
from pathlib import Path

# Ensure src/ is on the path
_src = Path(__file__).parent.parent / "src"
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.config import CONFIG_VERSION, TRIGGER_PRESETS, _validate_config
from whispy.core.engine import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
)
from whispy.hardware.event_decode import _KEYCODE_TO_NAME


class TestTriggerPresets:
    """The curated push-to-talk trigger presets exposed to the menu UI."""

    def test_every_preset_keycode_is_known(self):
        # The UI fallback names a configured trigger via keycode_to_name; every
        # non-default preset must resolve to a real entry (not keyNN).
        for label, value in TRIGGER_PRESETS:
            if value is None:
                continue
            assert value in _KEYCODE_TO_NAME, f"{label} keycode {value} missing from table"

    def test_no_preset_is_a_combination_string(self):
        # Modifier combinations stay valid hand-edited config values but are
        # deliberately not offered as presets (the listen-only tap cannot
        # swallow them). Every preset is the platform default or a keycode.
        for label, value in TRIGGER_PRESETS:
            assert value is None or (isinstance(value, int) and not isinstance(value, bool)), (
                f"{label} preset {value!r} is not None/keycode"
            )

    def test_fn_preset_value_is_none(self):
        # Fn stays None so resolve_trigger maps it to the platform default.
        assert TRIGGER_PRESETS[0] == ("Fn", None)


# ---------------------------------------------------------------------------
# min_recording_duration validation
# ---------------------------------------------------------------------------


class TestMinRecordingDuration:
    """Test validation of the min_recording_duration config key."""

    def test_default_present(self):
        assert DEFAULT_CONFIG["min_recording_duration"] == 0.3

    def test_valid_value_preserved(self):
        validated = _validate_config({"min_recording_duration": 0.5})
        assert validated["min_recording_duration"] == 0.5

    def test_negative_value_reset_to_default(self):
        validated = _validate_config({"min_recording_duration": -1})
        assert validated["min_recording_duration"] == 0.3

    def test_non_numeric_reset_to_default(self):
        validated = _validate_config({"min_recording_duration": "fast"})
        assert validated["min_recording_duration"] == 0.3

    def test_bool_reset_to_default(self):
        validated = _validate_config({"min_recording_duration": True})
        assert validated["min_recording_duration"] == 0.3


# ---------------------------------------------------------------------------
# save_config filtering
# ---------------------------------------------------------------------------


class TestSaveConfigFiltering:
    """Test that save_config filters unknown keys."""

    def test_unknown_keys_are_filtered(self, tmp_path):
        config = {**DEFAULT_CONFIG, "unknown_key": 42, "another_bad": "value"}
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert "unknown_key" not in saved
        assert "another_bad" not in saved

    def test_valid_configs_pass_through_unchanged(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["copy_to_clipboard"] = True
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert saved["copy_to_clipboard"] is True
        for key in DEFAULT_CONFIG:
            assert key in saved

    def test_mixed_valid_invalid_configs_save_only_valid(self, tmp_path):
        config = {
            "copy_to_clipboard": True,
            "min_recording_duration": 0.5,
            "unknown_key": "should_not_appear",
        }
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert saved["copy_to_clipboard"] is True
        assert saved["min_recording_duration"] == 0.5
        assert "unknown_key" not in saved

    def test_legacy_whisper_keys_are_dropped_not_fatal(self, tmp_path):
        """A config written before the Parakeet swap must still load.

        model_size / language / beam_size / best_of / auto_detect_min_duration
        configured the Whisper decoder and no longer exist. They are dropped
        like any other unknown key rather than raising.
        """
        config = {
            "model_size": "small",
            "language": "fr",
            "beam_size": 1,
            "best_of": 2,
            "auto_detect_min_duration": 0.5,
            "copy_to_clipboard": True,
        }
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        for legacy in ("model_size", "language", "beam_size", "best_of", "auto_detect_min_duration"):
            assert legacy not in saved
        assert saved["copy_to_clipboard"] is True

    def test_empty_config_uses_all_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config({}, config_path)

        saved = json.loads(config_path.read_text())
        for key in DEFAULT_CONFIG:
            assert saved[key] == DEFAULT_CONFIG[key]


# ---------------------------------------------------------------------------
# save_config file/directory permissions (harden-privacy-file-perms)
# ---------------------------------------------------------------------------


class TestSaveConfigPermissions:
    """save_config SHALL leave config.json at 0600 and its dir at 0700."""

    def test_fresh_save_sets_owner_only_permissions(self, tmp_path):
        config_dir = tmp_path / "whispy"
        config_path = config_dir / "config.json"
        save_config(dict(DEFAULT_CONFIG), config_path)

        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700

    def test_preexisting_world_readable_file_is_tightened(self, tmp_path):
        config_dir = tmp_path / "whispy"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.json"
        config_path.write_text("{}")
        os.chmod(config_path, 0o644)

        save_config(dict(DEFAULT_CONFIG), config_path)

        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    def test_chmod_failure_does_not_block_save(self, tmp_path, monkeypatch):
        config_path = tmp_path / "whispy" / "config.json"

        real_chmod = os.chmod

        def _raising_chmod(path, mode, *args, **kwargs):
            raise OSError("simulated chmod failure")

        monkeypatch.setattr(os, "chmod", _raising_chmod)
        try:
            save_config(dict(DEFAULT_CONFIG), config_path)
        finally:
            monkeypatch.setattr(os, "chmod", real_chmod)

        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["copy_to_clipboard"] == DEFAULT_CONFIG["copy_to_clipboard"]


# ---------------------------------------------------------------------------
# custom_vocabulary validation
# ---------------------------------------------------------------------------


class TestCustomVocabulary:
    """Test validation of the custom_vocabulary config key."""

    def test_default_is_empty_list(self):
        assert DEFAULT_CONFIG["custom_vocabulary"] == []

    def test_valid_list_preserved(self):
        validated = _validate_config({"custom_vocabulary": ["Whispy", "ctranslate2"]})
        assert validated["custom_vocabulary"] == ["Whispy", "ctranslate2"]

    def test_non_list_falls_back_to_empty(self):
        validated = _validate_config({"custom_vocabulary": "Whispy"})
        assert validated["custom_vocabulary"] == []

    def test_non_string_entries_filtered_and_stripped(self):
        validated = _validate_config({"custom_vocabulary": ["  Whispy  ", 42, "", None, "sox"]})
        assert validated["custom_vocabulary"] == ["Whispy", "sox"]


# ---------------------------------------------------------------------------
# Restart path resolution
# ---------------------------------------------------------------------------


class TestRestartPath:
    """Test that the restart path resolves correctly."""

    def test_restart_path_resolves_to_existing_file(self):
        """The restart path (whispy_daemon.py) should exist at project root."""
        from whispy.core.paths import resolve_daemon_script

        script_path = resolve_daemon_script()
        assert script_path.exists(), f"Restart script not found at {script_path}"

    def test_whispy_py_does_not_exist(self):
        """Verify whispy.py does NOT exist (should use whispy_daemon.py)."""
        from whispy.core.paths import resolve_daemon_script

        old_path = resolve_daemon_script().parent / "whispy.py"
        assert not old_path.exists(), "whispy.py should not exist"


# ---------------------------------------------------------------------------
# trigger_mode validation
# ---------------------------------------------------------------------------


class TestTriggerMode:
    """Test validation of the trigger_mode config key."""

    def test_default_is_hold(self):
        assert DEFAULT_CONFIG["trigger_mode"] == "hold"

    def test_hold_passes_through_unchanged(self):
        validated = _validate_config({"trigger_mode": "hold"})
        assert validated["trigger_mode"] == "hold"

    def test_toggle_passes_through_unchanged(self):
        validated = _validate_config({"trigger_mode": "toggle"})
        assert validated["trigger_mode"] == "toggle"

    def test_invalid_values_reset_to_hold(self):
        for bad in ("Toggle", "push", "", None, 123, True):
            validated = _validate_config({"trigger_mode": bad})
            assert validated["trigger_mode"] == "hold", f"{bad!r} should default to 'hold'"

    def test_missing_key_defaults_to_hold(self):
        validated = _validate_config({})
        assert validated["trigger_mode"] == "hold"

    def test_load_config_without_key_defaults_to_hold(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"copy_to_clipboard": True}))

        loaded = load_config(config_file)
        assert loaded["trigger_mode"] == "hold"

    def test_save_config_round_trips_toggle(self, tmp_path):
        config = dict(DEFAULT_CONFIG)
        config["trigger_mode"] = "toggle"
        config_path = tmp_path / "config.json"
        save_config(config, config_path)

        saved = json.loads(config_path.read_text())
        assert saved["trigger_mode"] == "toggle"


# ---------------------------------------------------------------------------
# Streaming / incremental transcription config
# ---------------------------------------------------------------------------


class TestStreamingConfig:
    """Validation and migration of the streaming config keys."""

    def test_defaults_present(self):
        assert DEFAULT_CONFIG["streaming_enabled"] is True
        assert DEFAULT_CONFIG["pause_ms"] == 600
        assert DEFAULT_CONFIG["min_speech_s"] == 0.7
        assert DEFAULT_CONFIG["min_chunk_s"] == 0.4
        assert DEFAULT_CONFIG["max_chunk_s"] == 8.0
        assert DEFAULT_CONFIG["vad_aggressiveness"] == 2

    def test_valid_values_preserved(self):
        validated = _validate_config(
            {
                "streaming_enabled": False,
                "pause_ms": 400,
                "min_speech_s": 1.2,
                "min_chunk_s": 0.5,
                "max_chunk_s": 20.0,
                "vad_aggressiveness": 3,
            }
        )
        assert validated["streaming_enabled"] is False
        assert validated["pause_ms"] == 400
        assert validated["min_speech_s"] == 1.2
        assert validated["min_chunk_s"] == 0.5
        assert validated["max_chunk_s"] == 20.0
        assert validated["vad_aggressiveness"] == 3

    def test_streaming_enabled_non_bool_resets(self):
        assert _validate_config({"streaming_enabled": "yes"})["streaming_enabled"] is True

    def test_pause_ms_non_positive_resets(self):
        assert _validate_config({"pause_ms": 0})["pause_ms"] == 600
        assert _validate_config({"pause_ms": -100})["pause_ms"] == 600
        assert _validate_config({"pause_ms": True})["pause_ms"] == 600

    def test_min_speech_s_invalid_resets(self):
        # 0 is legal (gate off); anything not a non-negative number is not.
        assert _validate_config({"min_speech_s": 0})["min_speech_s"] == 0
        assert _validate_config({"min_speech_s": -0.1})["min_speech_s"] == 0.7
        assert _validate_config({"min_speech_s": True})["min_speech_s"] == 0.7
        assert _validate_config({"min_speech_s": "0.7"})["min_speech_s"] == 0.7
        assert _validate_config({"min_speech_s": None})["min_speech_s"] == 0.7
        # Absent from the file -> the default.
        assert _validate_config({})["min_speech_s"] == 0.7

    def test_min_chunk_s_negative_resets(self):
        assert _validate_config({"min_chunk_s": -1})["min_chunk_s"] == 0.4

    def test_max_chunk_s_must_exceed_min_chunk_s(self):
        # max <= min is invalid -> reset to default
        assert _validate_config({"min_chunk_s": 5.0, "max_chunk_s": 3.0})["max_chunk_s"] == 8.0

    def test_vad_aggressiveness_out_of_range_resets(self):
        assert _validate_config({"vad_aggressiveness": 9})["vad_aggressiveness"] == 2
        assert _validate_config({"vad_aggressiveness": -1})["vad_aggressiveness"] == 2
        assert _validate_config({"vad_aggressiveness": True})["vad_aggressiveness"] == 2

    def test_migration_adds_streaming_keys(self, tmp_path):
        import json

        config_file = tmp_path / "config.json"
        # A pre-streaming config without the new keys.
        config_file.write_text(json.dumps({"copy_to_clipboard": False, "_version": 0}))

        loaded = load_config(config_file)
        for key in (
            "streaming_enabled",
            "pause_ms",
            "min_speech_s",
            "min_chunk_s",
            "max_chunk_s",
            "vad_aggressiveness",
        ):
            assert key in loaded
        # And the defaults were persisted back.
        on_disk = json.loads(config_file.read_text())
        assert "streaming_enabled" in on_disk


# ---------------------------------------------------------------------------
# soft_gap_ms config: the gap that releases the length-ceiling cut instead of
# falling at the very next frame (fix-dictation-text-fidelity, task 8.1)
# ---------------------------------------------------------------------------


class TestSoftGapMsConfig:
    """Validation of the soft_gap_ms config key."""

    def test_default_present(self):
        assert DEFAULT_CONFIG["soft_gap_ms"] == 350

    def test_default_on_no_file_load(self, tmp_path):
        # Scenario: The default soft gap is 350 milliseconds.
        loaded = load_config(tmp_path / "does-not-exist.json")
        assert loaded["soft_gap_ms"] == 350

    def test_missing_key_defaults(self):
        assert _validate_config({})["soft_gap_ms"] == 350

    def test_valid_value_preserved(self):
        assert _validate_config({"soft_gap_ms": 500})["soft_gap_ms"] == 500

    def test_zero_resets_to_default(self):
        assert _validate_config({"soft_gap_ms": 0})["soft_gap_ms"] == 350

    def test_negative_resets_to_default(self):
        assert _validate_config({"soft_gap_ms": -50})["soft_gap_ms"] == 350

    def test_string_resets_to_default(self):
        assert _validate_config({"soft_gap_ms": "350"})["soft_gap_ms"] == 350

    def test_bool_resets_to_default(self):
        # bool is an int subclass in Python; must be explicitly rejected.
        assert _validate_config({"soft_gap_ms": True})["soft_gap_ms"] == 350
        assert _validate_config({"soft_gap_ms": False})["soft_gap_ms"] == 350


# ---------------------------------------------------------------------------
# Type-while-speaking config (toggle mode only)
# ---------------------------------------------------------------------------


class TestTypeWhileSpeakingConfig:
    """Validation and migration of the type_while_speaking config key."""

    def test_default_present(self):
        assert DEFAULT_CONFIG["type_while_speaking"] is True

    def test_missing_key_migrated_to_true(self, tmp_path):
        config_file = tmp_path / "config.json"
        # A pre-existing config without the new key.
        config_file.write_text(json.dumps({"copy_to_clipboard": False, "_version": 0}))

        loaded = load_config(config_file)
        assert loaded["type_while_speaking"] is True
        # And the default was persisted back.
        on_disk = json.loads(config_file.read_text())
        assert on_disk["type_while_speaking"] is True

    def test_non_bool_resets_to_true(self):
        assert _validate_config({"type_while_speaking": "yes"})["type_while_speaking"] is True
        assert _validate_config({"type_while_speaking": 1})["type_while_speaking"] is True

    def test_explicit_false_preserved(self):
        assert _validate_config({"type_while_speaking": False})["type_while_speaking"] is False


# ---------------------------------------------------------------------------
# Text fidelity: clipboard-default + chunk ceiling, and the v1 -> v2 migration
# (fix-dictation-text-fidelity)
# ---------------------------------------------------------------------------


class TestTextFidelityDefaultsAndMigration:
    """copy_to_clipboard=True and max_chunk_s=8.0 are the new defaults; a v1
    config on disk is migrated to them once, and a deliberate value survives.
    """

    def test_new_defaults_on_no_file_load(self, tmp_path):
        # Scenario: Copy to clipboard is enabled by default.
        loaded = load_config(tmp_path / "does-not-exist.json")
        assert loaded["copy_to_clipboard"] is True
        assert loaded["max_chunk_s"] == 8.0

    def test_default_copy_to_clipboard_is_disabled_opt_out_survives_migration(self):
        # Kept under its original name from when False was the default; now
        # covers the explicit opt-out surviving migration (core-engine spec
        # scenario "Default copy to clipboard is disabled").
        config_file_payload = {"copy_to_clipboard": False, "_version": CONFIG_VERSION}
        validated = _validate_config(config_file_payload)
        assert validated["copy_to_clipboard"] is False

    def test_v1_config_is_migrated_to_clipboard_and_new_ceiling(self, tmp_path):
        # Scenario: An existing install is migrated to clipboard delivery.
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"copy_to_clipboard": False, "max_chunk_s": 12.0, "_version": 1}))

        loaded = load_config(config_file)
        assert loaded["copy_to_clipboard"] is True
        assert loaded["max_chunk_s"] == 8.0
        assert loaded["_version"] == CONFIG_VERSION

        on_disk = json.loads(config_file.read_text())
        assert on_disk["copy_to_clipboard"] is True
        assert on_disk["max_chunk_s"] == 8.0
        assert on_disk["_version"] == CONFIG_VERSION

    def test_migration_does_not_reapply_at_v2(self, tmp_path):
        # Scenario: Migration does not re-apply.
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"copy_to_clipboard": False, "_version": 2}))

        loaded = load_config(config_file)
        assert loaded["copy_to_clipboard"] is False

    def test_v1_tuned_max_chunk_s_survives_migration(self, tmp_path):
        # Scenario: A deliberately tuned chunk ceiling survives migration.
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"max_chunk_s": 20.0, "_version": 1}))

        loaded = load_config(config_file)
        assert loaded["max_chunk_s"] == 20.0
        # copy_to_clipboard migration is unconditional regardless of max_chunk_s.
        assert loaded["copy_to_clipboard"] is True
        assert loaded["_version"] == CONFIG_VERSION


# ---------------------------------------------------------------------------
# Migration backs up the file it replaces (fix-dictation-text-fidelity,
# tasks 8.4 / 8.5)
# ---------------------------------------------------------------------------


class TestMigrationBackup:
    """A migration copies the pre-migration file to a version-named ``.bak``
    beside it and logs which keys changed, before persisting the migrated
    result. A failed backup is logged but never blocks the migration.
    """

    def _full_v1_payload(self):
        # A "full" pre-migration config (every known key already present, as a
        # real saved file would be) so the only keys the migration itself
        # changes are copy_to_clipboard and max_chunk_s -- not every key that
        # merely happens to be missing from a sparse test fixture.
        payload = dict(DEFAULT_CONFIG)
        payload["copy_to_clipboard"] = False
        payload["max_chunk_s"] = 12.0
        payload["_version"] = 1
        return payload

    def test_backup_is_byte_identical_to_pre_migration_file(self, tmp_path):
        # Scenario: A migration backs up the file it replaces.
        config_file = tmp_path / "config.json"
        original_bytes = json.dumps(self._full_v1_payload()).encode()
        config_file.write_bytes(original_bytes)

        load_config(config_file)

        backup_file = tmp_path / "config.json.v1.bak"
        assert backup_file.exists()
        assert backup_file.read_bytes() == original_bytes

    def test_backup_named_v0_when_version_key_absent(self, tmp_path):
        # Scenario: A migration backs up the file it replaces (no _version key).
        config_file = tmp_path / "config.json"
        payload = dict(DEFAULT_CONFIG)
        payload["copy_to_clipboard"] = False
        payload.pop("_version", None)  # DEFAULT_CONFIG carries no _version key
        original_bytes = json.dumps(payload).encode()
        config_file.write_bytes(original_bytes)

        load_config(config_file)

        backup_file = tmp_path / "config.json.v0.bak"
        assert backup_file.exists()
        assert backup_file.read_bytes() == original_bytes

    def test_migration_logs_the_keys_it_changed(self, tmp_path, caplog):
        # Scenario: A migration backs up the file it replaces (keys logged).
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(self._full_v1_payload()))

        with caplog.at_level(logging.INFO, logger="whispy.core.config"):
            load_config(config_file)

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("copy_to_clipboard" in r.getMessage() and "max_chunk_s" in r.getMessage() for r in info_records)

    def test_backup_failure_is_logged_but_migration_still_persists(self, tmp_path, caplog, monkeypatch):
        # Scenario: A failed backup does not block the migration.
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(self._full_v1_payload()))

        def _raising_copy2(*args, **kwargs):
            raise OSError("simulated disk-full backup failure")

        monkeypatch.setattr(shutil, "copy2", _raising_copy2)

        with caplog.at_level(logging.WARNING, logger="whispy.core.config"):
            loaded = load_config(config_file)

        # The migration still ran and persisted despite the backup failure.
        assert loaded["copy_to_clipboard"] is True
        assert loaded["max_chunk_s"] == 8.0
        assert loaded["_version"] == CONFIG_VERSION
        on_disk = json.loads(config_file.read_text())
        assert on_disk["copy_to_clipboard"] is True
        assert on_disk["_version"] == CONFIG_VERSION

        # No backup was written, and the failure was logged at WARNING.
        assert not (tmp_path / "config.json.v1.bak").exists()
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_an_already_migrated_config_is_not_rewritten_or_re_backed_up(self, tmp_path):
        """The backup must survive the launches that follow the migration.

        Migrating on every load would copy the already-migrated file over
        ``config.json.v1.bak`` on the next start, replacing the only snapshot of
        what the user had before the upgrade with a copy of what they have now.
        """
        from whispy.core.config import load_config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"copy_to_clipboard": False, "max_chunk_s": 12.0, "_version": 1}))

        load_config(config_file)  # the real v1 -> v2 migration

        backup = tmp_path / "config.json.v1.bak"
        assert json.loads(backup.read_text())["copy_to_clipboard"] is False
        backup_mtime = backup.stat().st_mtime_ns
        config_mtime = config_file.stat().st_mtime_ns

        load_config(config_file)  # every later launch

        assert backup.stat().st_mtime_ns == backup_mtime, "the backup must not be rewritten"
        assert config_file.stat().st_mtime_ns == config_mtime, "a no-op migration must not write"
        assert json.loads(backup.read_text())["copy_to_clipboard"] is False
        assert not (tmp_path / "config.json.v2.bak").exists()


class TestStaleStreamingDisabledMigration:
    """v2 -> v3: a leftover ``streaming_enabled: false`` no longer silences live typing."""

    def test_live_typing_config_gets_streaming_back_once_with_a_backup(self, tmp_path):
        from whispy.core.config import load_config

        config_file = tmp_path / "config.json"
        stale = {"type_while_speaking": True, "streaming_enabled": False, "_version": 2}
        config_file.write_text(json.dumps(stale))

        loaded = load_config(config_file)

        assert loaded["streaming_enabled"] is True
        assert json.loads(config_file.read_text())["streaming_enabled"] is True
        assert json.loads((tmp_path / "config.json.v2.bak").read_text()) == stale

    def test_streaming_disabled_by_hand_after_the_migration_is_left_alone(self, tmp_path):
        from whispy.core.config import load_config

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"type_while_speaking": True, "streaming_enabled": False, "_version": CONFIG_VERSION})
        )

        assert load_config(config_file)["streaming_enabled"] is False

    def test_streaming_disabled_without_live_typing_is_left_alone(self, tmp_path):
        from whispy.core.config import load_config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"type_while_speaking": False, "streaming_enabled": False, "_version": 2}))

        assert load_config(config_file)["streaming_enabled"] is False


# ---------------------------------------------------------------------------
# read_config: the non-migrating read path (fix-config-merge-on-save)
# ---------------------------------------------------------------------------


class TestReadConfig:
    """read_config returns the validated on-disk config without ever writing.

    load_config migrates, and _migrate_config persists. Config updates re-read
    the file to merge onto it, so they need a read that does not turn every
    update into an extra write of a file the user may be hand-editing.
    """

    def _config_file(self, tmp_path, payload):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(payload))
        return config_file

    def test_read_does_not_write_a_file_that_load_would_migrate(self, tmp_path):
        from whispy.core.config import read_config

        # No _version key, so load_config would migrate and persist.
        config_file = self._config_file(tmp_path, {"pause_ms": 900})
        before = config_file.stat().st_mtime_ns
        original = config_file.read_text()

        assert read_config(config_file)["pause_ms"] == 900

        assert config_file.stat().st_mtime_ns == before, "read_config must not write"
        assert config_file.read_text() == original

    def test_load_config_still_migrates(self, tmp_path):
        # Guards the split: boot behaviour must be unchanged.
        config_file = self._config_file(tmp_path, {"pause_ms": 900})
        loaded = load_config(config_file)
        assert loaded["pause_ms"] == 900
        on_disk = json.loads(config_file.read_text())
        assert "_version" in on_disk, "load_config must still migrate and persist"

    def test_read_fills_missing_keys_with_defaults(self, tmp_path):
        from whispy.core.config import DEFAULT_CONFIG, read_config

        config_file = self._config_file(tmp_path, {"pause_ms": 900})
        loaded = read_config(config_file)
        assert set(loaded) >= set(DEFAULT_CONFIG)
        assert loaded["max_chunk_s"] == DEFAULT_CONFIG["max_chunk_s"]

    def test_read_degrades_a_malformed_value_to_its_default(self, tmp_path):
        # This is what keeps a hand-edit from merging in unchecked.
        from whispy.core.config import DEFAULT_CONFIG, read_config

        config_file = self._config_file(tmp_path, {"vad_aggressiveness": "loud", "pause_ms": 900})
        loaded = read_config(config_file)
        assert loaded["vad_aggressiveness"] == DEFAULT_CONFIG["vad_aggressiveness"]
        # A valid sibling key in the same file is unaffected.
        assert loaded["pause_ms"] == 900

    def test_read_of_a_corrupt_file_returns_defaults_without_raising(self, tmp_path):
        from whispy.core.config import DEFAULT_CONFIG, read_config

        config_file = tmp_path / "config.json"
        config_file.write_text("{ not json")
        loaded = read_config(config_file)
        assert loaded["max_chunk_s"] == DEFAULT_CONFIG["max_chunk_s"]

    def test_read_of_a_missing_file_returns_defaults(self, tmp_path):
        from whispy.core.config import DEFAULT_CONFIG, read_config

        loaded = read_config(tmp_path / "does-not-exist.json")
        assert loaded == dict(DEFAULT_CONFIG) or set(loaded) >= set(DEFAULT_CONFIG)

    def test_an_unreadable_file_falls_back_to_the_caller_s_config(self, tmp_path):
        from whispy.core.config import DEFAULT_CONFIG, read_config

        config_file = tmp_path / "config.json"
        config_file.write_text("{ not json")
        running = dict(DEFAULT_CONFIG, pause_ms=950)

        loaded = read_config(config_file, fallback=running)

        assert loaded["pause_ms"] == 950

    def test_the_fallback_is_validated_like_any_other_source(self, tmp_path):
        from whispy.core.config import DEFAULT_CONFIG, read_config

        config_file = tmp_path / "config.json"
        config_file.write_text("{ not json")
        running = dict(DEFAULT_CONFIG, vad_aggressiveness="loud")

        loaded = read_config(config_file, fallback=running)

        assert loaded["vad_aggressiveness"] == DEFAULT_CONFIG["vad_aggressiveness"]

    def test_a_readable_file_ignores_the_fallback(self, tmp_path):
        from whispy.core.config import DEFAULT_CONFIG, read_config

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"pause_ms": 700}))

        loaded = read_config(config_file, fallback=dict(DEFAULT_CONFIG, pause_ms=950))

        assert loaded["pause_ms"] == 700

"""Tests for the persistent correction store and diff-based extraction."""

import json
import os
import stat

import pytest

from whispy.core.corrections import CorrectionStore, extract_corrections


class TestCorrectionStore:
    @pytest.fixture(autouse=True)
    def _enable_learning(self, monkeypatch):
        # These tests validate the underlying learning machinery, which is
        # gated off by default (see TestAdaptiveLearningGate). Enable it so the
        # hotwords/apply/track mechanics are exercised.
        monkeypatch.setattr("whispy.core.corrections.ADAPTIVE_LEARNING_ENABLED", True)

    def test_store_empty_on_missing_file(self, tmp_path):
        store = CorrectionStore(tmp_path / "missing" / "corrections.json")
        assert store.all_entries() == {}

    def test_add_and_retrieve(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.add_correction("wispy", "Whispy")
        entries = store.all_entries()
        assert "wispy" in entries
        assert entries["wispy"]["replacement"] == "Whispy"

    def test_add_correction_case_insensitive(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.add_correction("WISPY", "Whispy")
        entries = store.all_entries()
        assert "wispy" in entries
        assert "WISPY" not in entries

    def test_add_correction_increments_count(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.add_correction("wispy", "Whispy")
        store.add_correction("wispy", "Whispy")
        assert store.all_entries()["wispy"]["corrections_count"] == 2

    def test_remove_correction(self, tmp_path):
        path = tmp_path / "corrections.json"
        store = CorrectionStore(path)
        store.add_correction("wispy", "Whispy")
        store.remove("wispy")
        assert store.all_entries() == {}
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert "wispy" not in on_disk["corrections"]

    def test_corrupt_file_handled(self, tmp_path):
        path = tmp_path / "corrections.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = CorrectionStore(path)
        assert store.all_entries() == {}

    def test_atomic_save(self, tmp_path):
        path = tmp_path / "corrections.json"
        store = CorrectionStore(path)
        store.add_correction("wispy", "Whispy")
        assert path.exists()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["corrections"]["wispy"]["replacement"] == "Whispy"

    def test_hotwords_sorted_by_count(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.add_correction("zzz", "Zzzcorrected")
        store.add_correction("aaa", "Aaacorrected")
        store.add_correction("aaa", "Aaacorrected")
        store.add_correction("aaa", "Aaacorrected")
        result = store.hotwords()
        assert result.index("Aaacorrected") < result.index("Zzzcorrected")

    def test_hotwords_budget_limit(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        for _ in range(3):
            store.add_correction("wrong1", "one")
        for _ in range(2):
            store.add_correction("wrong2", "two")
        store.add_correction("wrong3", "three")
        result = store.hotwords(max_tokens=2)
        words = result.split()
        assert len(words) == 2
        assert words == ["one", "two"]

    def test_hotwords_empty_store(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        assert store.hotwords() == ""

    def test_apply_corrections_below_threshold(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.add_correction("wispy", "Whispy")
        store.add_correction("wispy", "Whispy")
        result = store.apply_corrections("hello wispy world")
        assert result == "hello wispy world"

    def test_apply_corrections_above_threshold(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        for _ in range(3):
            store.add_correction("wispy", "Whispy")
        result = store.apply_corrections("hello wispy world")
        assert result == "hello Whispy world"

    def test_apply_corrections_word_boundary(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        for _ in range(3):
            store.add_correction("wispy", "Whispy")
        result = store.apply_corrections("wispython is a library")
        assert result == "wispython is a library"

    def test_apply_corrections_case_insensitive(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        for _ in range(3):
            store.add_correction("wispy", "Whispy")
        result = store.apply_corrections("WISPY rocks")
        assert result == "Whispy rocks"

    def test_track_occurrences(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.add_correction("wispy", "Whispy")
        store.track_occurrences("I said wispy today")
        assert store.all_entries()["wispy"]["occurrences"] == 1

    def test_increment_occurrence_unknown_word(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store.increment_occurrence("unknownword")
        assert "unknownword" not in store.all_entries()


class TestCorrectionStorePermissions:
    """corrections.json and its parent dir SHALL end up owner-only (harden-privacy-file-perms)."""

    def test_fresh_save_sets_owner_only_permissions(self, tmp_path):
        corrections_dir = tmp_path / "whispy"
        path = corrections_dir / "corrections.json"
        store = CorrectionStore(path)
        store.add_correction("wispy", "Whispy")

        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(corrections_dir.stat().st_mode) == 0o700

    def test_preexisting_world_readable_file_is_tightened(self, tmp_path):
        path = tmp_path / "corrections.json"
        path.write_text(json.dumps({"version": 1, "corrections": {}}))
        os.chmod(path, 0o644)

        store = CorrectionStore(path)
        store.add_correction("wispy", "Whispy")

        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_replace_failure_propagates_and_cleans_up_tmp(self, tmp_path, monkeypatch):
        path = tmp_path / "corrections.json"
        store = CorrectionStore(path)

        def _raising_replace(*_args, **_kwargs):
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", _raising_replace)
        with pytest.raises(OSError, match="simulated replace failure"):
            store.add_correction("wispy", "Whispy")

        assert list(tmp_path.glob("*.tmp")) == []

    def test_replace_keyboard_interrupt_propagates_immediately(self, tmp_path, monkeypatch):
        path = tmp_path / "corrections.json"
        store = CorrectionStore(path)

        def _raising_replace(*_args, **_kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(os, "replace", _raising_replace)
        with pytest.raises(KeyboardInterrupt):
            store.add_correction("wispy", "Whispy")


class TestExtractCorrections:
    def test_extract_no_change(self):
        assert extract_corrections("hello world", "hello world today") == {}

    def test_extract_single_word_correction(self):
        result = extract_corrections("wispy is great", "Hello Whispy is great")
        assert result == {"wispy": "Whispy"}

    def test_extract_empty_inputs(self):
        assert extract_corrections("", "hello world") == {}
        assert extract_corrections("hello world", "") == {}

    def test_extract_field_too_short(self):
        assert extract_corrections("hello world today", "hello world") == {}

    def test_extract_low_match(self):
        assert extract_corrections("aaa bbb ccc ddd", "wxy wxz wxq wxr") == {}


class TestAdaptiveLearningGate:
    """Adaptive learning is disabled by default: the poison loop (mislearned
    word→word shifts fed back to Whisper as hotwords) must be fully inert until
    the alignment algorithm is rewritten."""

    def test_hotwords_disabled_returns_empty(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        # Even with entries present on disk, disabled hotwords feed nothing.
        store._data = {"foo": {"replacement": "│", "corrections_count": 5}}
        assert store.hotwords() == ""

    def test_apply_corrections_disabled_is_noop(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store._data = {"le": {"replacement": "bruno", "corrections_count": 9}}
        assert store.apply_corrections("le chat") == "le chat"

    def test_track_occurrences_disabled_is_noop(self, tmp_path):
        store = CorrectionStore(tmp_path / "corrections.json")
        store._data = {"le": {"replacement": "bruno", "corrections_count": 9, "occurrences": 0}}
        store.track_occurrences("le le le")
        assert store._data["le"]["occurrences"] == 0

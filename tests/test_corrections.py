"""Tests for the persistent correction store and diff-based extraction."""

import json

from whispy.core.corrections import CorrectionStore, extract_corrections


class TestCorrectionStore:
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

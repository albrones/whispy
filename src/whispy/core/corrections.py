"""Persistent correction store and post-transcription replacement.

Learns from user corrections detected by the snapshot-diff system:
tracks wrong→right word mappings with occurrence counts, feeds them
to faster-whisper as hotwords, and applies deterministic replacements
once confidence is high enough.
"""

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CORRECTIONS_VERSION = 1
AUTO_REPLACE_THRESHOLD = 3
_DEFAULT_PATH = Path.home() / ".config" / "whispy" / "corrections.json"


class CorrectionStore:
    """Persistent store for learned transcription corrections."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = raw.get("corrections", {})
        except FileNotFoundError:
            self._data = {}
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("[corrections] corrupt file, starting fresh")
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": CORRECTIONS_VERSION, "corrections": self._data},
            ensure_ascii=False,
            indent=2,
        )
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            os.write(fd, payload.encode("utf-8"))
            os.close(fd)
            os.replace(tmp, self._path)
        except BaseException:
            os.close(fd) if not os.get_inheritable(fd) else None
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_correction(self, wrong: str, right: str) -> None:
        """Record a detected correction. Case-insensitive key."""
        key = wrong.lower()
        entry = self._data.setdefault(key, {"replacement": right, "occurrences": 0, "corrections_count": 0})
        entry["replacement"] = right
        entry["corrections_count"] = entry.get("corrections_count", 0) + 1
        self._save()

    def increment_occurrence(self, word: str) -> None:
        """Bump occurrence count for a known wrong word seen in transcription output."""
        key = word.lower()
        if key in self._data:
            self._data[key]["occurrences"] = self._data[key].get("occurrences", 0) + 1
            self._save()

    def remove(self, key: str) -> None:
        """Remove a correction entry."""
        self._data.pop(key.lower(), None)
        self._save()

    def all_entries(self) -> dict[str, dict[str, Any]]:
        """Return all correction entries (read-only view)."""
        return dict(self._data)

    def hotwords(self, max_tokens: int = 200) -> str:
        """Build a hotwords string from entries with corrections_count >= 1.

        Sorted by corrections_count descending, truncated to fit the token
        budget (approximate: 1 word ≈ 1 token for proper nouns).
        """
        eligible = [(k, v) for k, v in self._data.items() if v.get("corrections_count", 0) >= 1]
        eligible.sort(key=lambda x: x[1].get("corrections_count", 0), reverse=True)
        words: list[str] = []
        budget = max_tokens
        for _key, entry in eligible:
            word = entry["replacement"]
            cost = len(word.split())
            if budget - cost < 0:
                break
            words.append(word)
            budget -= cost
        return " ".join(words) if words else ""

    def apply_corrections(self, text: str) -> str:
        """Case-insensitive whole-word replacement for high-confidence entries."""
        if not text or not self._data:
            return text
        for key, entry in self._data.items():
            if entry.get("corrections_count", 0) < AUTO_REPLACE_THRESHOLD:
                continue
            pattern = re.compile(r"\b" + re.escape(key) + r"\b", re.IGNORECASE)
            text = pattern.sub(entry["replacement"], text)
        return text

    def track_occurrences(self, text: str) -> None:
        """Increment occurrence count for any known wrong words found in text."""
        if not text or not self._data:
            return
        text_lower = text.lower()
        for key in self._data:
            if re.search(r"\b" + re.escape(key) + r"\b", text_lower):
                self._data[key]["occurrences"] = self._data[key].get("occurrences", 0) + 1
        self._save()


def extract_corrections(injected: str, field_value: str) -> dict[str, str]:
    """Extract word-level corrections by finding the injected text's best
    alignment in the current field value.

    Returns ``{lowercase_wrong: corrected_form}`` for changed words, or
    empty dict when no correction is detected.
    """
    if not injected or not field_value:
        return {}
    if injected in field_value:
        return {}

    injected_words = injected.split()
    if not injected_words:
        return {}

    field_words = field_value.split()
    window = len(injected_words)
    if len(field_words) < window:
        return {}

    best_match = 0
    best_offset = -1
    for i in range(len(field_words) - window + 1):
        matches = sum(1 for j in range(window) if field_words[i + j].lower() == injected_words[j].lower())
        if matches > best_match:
            best_match = matches
            best_offset = i

    if best_offset == -1 or best_match < max(1, window // 2):
        return {}

    corrections = {}
    for j in range(window):
        old = injected_words[j]
        new = field_words[best_offset + j]
        if old.lower() != new.lower():
            corrections[old.lower()] = new
    return corrections

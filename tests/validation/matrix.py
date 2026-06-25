"""Parse and lint ``FEATURE_MATRIX.md`` — the single source of truth.

The matrix maps every user-facing feature to its platform(s), coverage tier,
what verifies it, and notes. This module parses that table, lints it (required
columns, resolvable ``Verified by`` targets), and exposes the ``manual-ui`` rows
from which the operator checklist is generated.

Pure except for the filesystem reads used to resolve ``Verified by`` targets
(tier: unit-pure — driven by a fixture matrix in tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = ["Feature", "Platform(s)", "Tier", "Verified by", "Notes"]
VALID_TIERS = {"unit-pure", "unit-mocked", "live-driven", "macos-real", "linux-real", "manual-ui"}

# Repo root = three levels up from this file (tests/validation/matrix.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX_PATH = REPO_ROOT / "FEATURE_MATRIX.md"


@dataclass
class Row:
    feature: str
    platforms: str
    tier: str
    verified_by: str
    notes: str

    @property
    def refs(self) -> list[str]:
        """Split the ``Verified by`` cell into individual references."""
        return [r.strip().strip("`") for r in self.verified_by.split(",") if r.strip()]


def parse_matrix(path: Path | None = None) -> list[Row]:
    """Parse the ``## Matrix`` table into Row objects."""
    text = (path or DEFAULT_MATRIX_PATH).read_text(encoding="utf-8")
    rows: list[Row] = []
    in_table = False
    header_seen = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break  # table ended
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        # The header row contains "Feature"; the next line is the |---| divider.
        if not header_seen:
            if cells and cells[0] == "Feature":
                header_seen = True
                in_table = True
            continue
        if set("".join(cells)) <= set("-: "):
            continue  # divider row
        if len(cells) < 5:
            continue
        rows.append(Row(cells[0], cells[1], cells[2], cells[3], cells[4]))
    return rows


def manual_ui_rows(path: Path | None = None) -> list[Row]:
    """Rows tagged ``manual-ui`` — the source of the operator checklist."""
    return [r for r in parse_matrix(path) if r.tier == "manual-ui"]


def _ref_is_resolvable(ref: str, tier: str, repo_root: Path) -> tuple[bool, str]:
    """Return (ok, reason) for a single ``Verified by`` reference."""
    if ref in ("TODO", "none", ""):
        return False, "no verification yet (gap)"
    if ref == "operator":
        if tier != "manual-ui":
            return False, "'operator' is only valid on manual-ui rows"
        return True, ""
    if ref == "doctor":
        return True, ""
    # Otherwise treat it as a pytest target: path[::node]. The file must exist.
    file_part = ref.split("::", 1)[0]
    target = repo_root / file_part
    if target.exists():
        return True, ""
    return False, f"target not found: {file_part}"


def lint_matrix(path: Path | None = None, repo_root: Path | None = None) -> list[str]:
    """Return a list of human-readable lint issues; empty means clean."""
    path = path or DEFAULT_MATRIX_PATH
    repo_root = repo_root or REPO_ROOT
    issues: list[str] = []
    rows = parse_matrix(path)
    if not rows:
        return ["matrix has no rows"]
    seen: set[tuple[str, str]] = set()
    for r in rows:
        key = (r.feature, r.platforms)
        if key in seen:
            issues.append(f"duplicate row: {r.feature} ({r.platforms})")
        seen.add(key)
        if r.tier not in VALID_TIERS:
            issues.append(f"{r.feature} ({r.platforms}): unknown tier '{r.tier}'")
        if not r.refs:
            issues.append(f"{r.feature} ({r.platforms}): empty 'Verified by'")
        for ref in r.refs:
            ok, reason = _ref_is_resolvable(ref, r.tier, repo_root)
            if not ok:
                issues.append(f"{r.feature} ({r.platforms}): {reason}")
    return issues

"""Structural test for the Homebrew formula (packaging/homebrew/whispy.rb).

CI has no Ruby toolchain, so we guard the formula as text: the fields the
docs (docs/homebrew.md) and the release pipeline (release.yml) depend on must
stay present. In particular release.yml rewrites a single ``url`` line and a
single ``sha256`` line with a count=1 regex — if either is duplicated or
removed, the per-release bump silently patches the wrong thing.
"""

import re
from pathlib import Path

import pytest

FORMULA = Path(__file__).resolve().parent.parent / "packaging" / "homebrew" / "whispy.rb"


@pytest.fixture(scope="module")
def formula() -> str:
    return FORMULA.read_text(encoding="utf-8")


def test_formula_exists():
    assert FORMULA.is_file(), "packaging/homebrew/whispy.rb is missing"


@pytest.mark.parametrize(
    "field",
    ["desc", "homepage", "url", "sha256", "license", "service do", "test do"],
)
def test_required_fields_present(formula: str, field: str):
    assert field in formula, f"formula missing required field: {field}"


@pytest.mark.parametrize("dep", ['depends_on "python@3.12"'])
def test_required_dependencies(formula: str, dep: str):
    assert dep in formula, f"formula missing dependency: {dep}"


def test_no_sox_dependency(formula: str):
    # Audio uses sounddevice/PortAudio (a Python dep); sox is no longer required.
    assert 'depends_on "sox"' not in formula, "formula must not depend on sox"


def test_single_url_line_for_release_bump(formula: str):
    # release.yml patches the url line with re.sub(..., count=1).
    url_lines = re.findall(r'^\s*url\s+".*"\s*$', formula, flags=re.M)
    assert len(url_lines) == 1, f"expected exactly one url line, found {len(url_lines)}"


def test_single_sha256_line_for_release_bump(formula: str):
    sha_lines = re.findall(r'^\s*sha256\s+".*"\s*$', formula, flags=re.M)
    assert len(sha_lines) == 1, f"expected exactly one sha256 line, found {len(sha_lines)}"

"""Doc-code parity guard tests.

Mirrors the ``tests/test_website.py`` pattern (plain pytest functions reading
doc files as text) but scoped to README.md, AGENTS.md, CHANGELOG.md, and the
``tests/`` directory listing, so the highest-value, cheapest-to-check facts
in the non-website docs can't silently drift from the code again (see
``openspec/changes/sync-docs-with-code``).
"""

import re
from pathlib import Path

import pytest

from whispy.core.config import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
CHANGELOG = ROOT / "CHANGELOG.md"
TESTS_DIR = ROOT / "tests"

FRENCH_MARKERS = [
    "Non publié",
    "Ajoutés",
    "Changés",
    "Corrigés",
    "Supprimés",
    "Modifiés",
    "Critères de sortie",
    "Date de release",
]


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def agents() -> str:
    return AGENTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def changelog() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return the body of the first `## <heading>` section (up to the next `## `)."""
    match = re.search(rf"^## .*{re.escape(heading)}.*$", text, re.MULTILINE)
    assert match is not None, f"section heading containing {heading!r} not found"
    start = match.end()
    next_heading = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def _config_table_keys(readme_text: str) -> set[str]:
    section = _section(readme_text, "Configuration")
    return set(re.findall(r"^\|\s*`([a-zA-Z_]+)`\s*\|", section, re.MULTILINE))


def _test_table_paths(readme_text: str) -> list[str]:
    section = _section(readme_text, "Testing")
    return re.findall(r"`(tests/[^`]+\.py(?:::[^`]+)?)`", section)


# --- Documented defaults match code -----------------------------------------


def test_readme_language_default_matches_config(readme: str):
    """README-documented `language` default equals DEFAULT_CONFIG['language']."""
    section = _section(readme, "Configuration")
    match = re.search(r"`language`\s*\|\s*`([a-zA-Z_-]+)`", section)
    assert match is not None, "language row not found in the README Configuration table"
    assert match.group(1) == DEFAULT_CONFIG["language"]


# --- Complete config key reference ------------------------------------------


def test_readme_config_table_covers_every_default_config_key(readme: str):
    documented = _config_table_keys(readme)
    missing = set(DEFAULT_CONFIG.keys()) - documented
    assert not missing, f"DEFAULT_CONFIG keys missing from the README Configuration table: {missing}"


# --- API examples are authenticated and correctly attributed ---------------


def test_readme_port_attribution(readme: str):
    assert "defined near the top of `src/whispy/api/server.py`" in readme
    assert "defined near the top of `whispy_daemon.py`" not in readme


def test_agents_curl_examples_include_auth_header(agents: str):
    """Every curl example against the local API includes the bearer-token header."""
    curl_lines = [line for line in agents.splitlines() if "curl" in line and "localhost:9090" in line]
    assert curl_lines, "expected at least one curl example against the local API in AGENTS.md"
    for line in curl_lines:
        assert "Authorization: Bearer" in line, f"curl example missing auth header: {line!r}"


def test_install_sh_smoke_test_curl_includes_auth_header():
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    curl_lines = [line for line in install_sh.splitlines() if "curl" in line and "localhost:9090" in line]
    assert curl_lines, "expected a smoke-test curl example in install.sh"
    for line in curl_lines:
        assert "Authorization: Bearer" in line, f"curl example missing auth header: {line!r}"


# --- Platform description reflects cross-platform support ------------------


def test_agents_platform_line_not_macos_only(agents: str):
    assert "macOS (Apple Silicon/Intel) only" not in agents
    assert "Linux" in agents


def test_agents_lists_linux_dependencies(agents: str):
    for dep in ("pynput", "pystray", "Pillow"):
        assert dep in agents, f"{dep} missing from AGENTS.md tech-stack list"


# --- Test suite documentation matches the tests/ directory -----------------


def test_readme_test_table_paths_exist(readme: str):
    for path in _test_table_paths(readme):
        file_path = path.split("::")[0]
        assert (ROOT / file_path).is_file(), f"README references nonexistent test file: {file_path}"


def test_readme_does_not_reference_test_stress(readme: str):
    assert "test_stress.py" not in readme


def test_readme_error_handling_description_has_no_sox_claim(readme: str):
    section = _section(readme, "Testing")
    line = next((li for li in section.splitlines() if "test_error_handling.py" in li), None)
    assert line is not None, "test_error_handling.py row not found in README test table"
    assert "sox" not in line.lower()


# --- Feature documentation parity -------------------------------------------


def test_feature_matrix_has_adaptive_vocabulary_row():
    feature_matrix = (ROOT / "FEATURE_MATRIX.md").read_text(encoding="utf-8")
    assert "test_corrections.py" in feature_matrix
    assert re.search(r"[Aa]daptive vocabulary|[Cc]orrection learning", feature_matrix)


def test_readme_mentions_adaptive_vocabulary_feature(readme: str):
    assert re.search(r"[Ll]earns your words|correct.*transcription.*remember", readme)


# --- CHANGELOG is English-only with a single open section ------------------


def test_changelog_has_no_french_markers(changelog: str):
    found = [marker for marker in FRENCH_MARKERS if marker in changelog]
    assert not found, f"French-language markers found in CHANGELOG.md: {found}"


def test_changelog_has_exactly_one_unreleased_section(changelog: str):
    assert changelog.count("## [Unreleased]") == 1

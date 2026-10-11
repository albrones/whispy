"""Doc-code parity guard tests.

Mirrors the ``tests/test_website.py`` pattern (plain pytest functions reading
doc files as text) but scoped to README.md, AGENTS.md, CHANGELOG.md, and the
``tests/`` directory listing, so the highest-value, cheapest-to-check facts
in the non-website docs can't silently drift from the code again (see
``openspec/changes/sync-docs-with-code``).
"""

import html
import json
import re
from pathlib import Path

import pytest

from whispy.core.config import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
TESTS_DIR = ROOT / "tests"
DOCS_DIR = ROOT / "website" / "docs"
DOCS_BASE = "https://whispy-dun.vercel.app/docs/"
INSTALL_ONE_LINER = "curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash"

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
def contributing() -> str:
    return CONTRIBUTING.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config_rows() -> dict[str, str]:
    """Map each documented config key to its Default cell text (HTML-unescaped)."""
    page = (DOCS_DIR / "config.html").read_text(encoding="utf-8")
    table = re.search(r'<table id="config-reference">(.*?)</table>', page, re.DOTALL)
    assert table is not None, "config.html has no config-reference table"
    rows = {}
    for key, cells in re.findall(r'<tr id="cfg-([^"]+)">(.*?)</tr>', table.group(1), re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", cells, re.DOTALL)
        default = re.sub(r"</?code>", "", tds[1])
        rows[key] = html.unescape(default)
    return rows


@pytest.fixture(scope="module")
def usage_page() -> str:
    return (DOCS_DIR / "usage.html").read_text(encoding="utf-8")


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


def _test_table_paths(contributing_text: str) -> list[str]:
    section = _section(contributing_text, "Test suite")
    return re.findall(r"`(tests/[^`]+\.py(?:::[^`]+)?)`", section)


# --- Documented defaults match code -----------------------------------------


def test_docs_do_not_document_removed_config_keys(config_rows: dict[str, str]):
    """Keys that configured the Whisper decoder must not appear as settings."""
    for gone in ("model_size", "language", "beam_size", "best_of", "auto_detect_min_duration"):
        assert gone not in config_rows, f"config docs still document the removed `{gone}` setting"


def test_readme_names_the_model_that_actually_runs(readme: str):
    """The README must present Parakeet as the engine, not Whisper.

    faster-whisper may still be *named* — the upgrade note points at the stale
    model cache — but never as the thing that transcribes.
    """
    lowered = readme.lower()
    assert "parakeet" in lowered

    for line in lowered.splitlines():
        if "faster-whisper" not in line:
            continue
        # Allowed: the stale-cache path and the sentence retiring it.
        assert "no longer used" in line or "models--systran--faster-whisper" in line, (
            f"README still presents faster-whisper as the engine: {line.strip()!r}"
        )


# --- Complete config key reference ------------------------------------------


def test_config_docs_cover_every_default_config_key(config_rows: dict[str, str]):
    missing = set(DEFAULT_CONFIG.keys()) - set(config_rows)
    assert not missing, f"DEFAULT_CONFIG keys missing from docs/config.html: {missing}"


def test_config_docs_defaults_match_code(config_rows: dict[str, str]):
    for key, default in DEFAULT_CONFIG.items():
        assert config_rows[key] == json.dumps(default), (
            f"docs default for `{key}` is {config_rows[key]!r}, code says {json.dumps(default)!r}"
        )


# --- API examples are authenticated and correctly attributed ---------------


def test_usage_docs_port_attribution(usage_page: str):
    assert "defined near the top of <code>src/whispy/api/server.py</code>" in usage_page
    assert "defined near the top of <code>whispy_daemon.py</code>" not in usage_page


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


def test_contributing_test_table_paths_exist(contributing: str):
    paths = _test_table_paths(contributing)
    assert paths, "CONTRIBUTING.md test table lists no test files"
    for path in paths:
        file_path = path.split("::")[0]
        assert (ROOT / file_path).is_file(), f"CONTRIBUTING references nonexistent test file: {file_path}"


def test_contributing_does_not_reference_test_stress(contributing: str):
    assert "test_stress.py" not in contributing


def test_contributing_error_handling_description_has_no_sox_claim(contributing: str):
    section = _section(contributing, "Test suite")
    line = next((li for li in section.splitlines() if "test_error_handling.py" in li), None)
    assert line is not None, "test_error_handling.py row not found in CONTRIBUTING test table"
    assert "sox" not in line.lower()


# --- README stays short and points at the docs -----------------------------


def test_readme_is_short(readme: str):
    assert len(readme.splitlines()) <= 120


@pytest.mark.parametrize("page", ["install.html", "troubleshooting.html", "config.html", "usage.html"])
def test_readme_links_to_docs_pages(readme: str, page: str):
    assert DOCS_BASE + page in readme, f"README must link to the docs {page} page"


def test_readme_has_no_config_table(readme: str):
    assert "## Configuration" not in readme
    assert not re.search(r"^\|\s*`copy_to_clipboard`\s*\|", readme, re.MULTILINE)


def test_readme_one_liner_precedes_documentation_heading(readme: str):
    assert INSTALL_ONE_LINER in readme
    assert "## Documentation" in readme
    assert readme.index(INSTALL_ONE_LINER) < readme.index("## Documentation")


# --- Feature documentation parity -------------------------------------------


def test_docs_do_not_advertise_correction_learning(readme: str):
    """The adaptive-correction feature was removed (tracked in issue #8);
    docs must not claim Whispy learns from corrections."""
    feature_matrix = (ROOT / "FEATURE_MATRIX.md").read_text(encoding="utf-8")
    for doc in (readme, feature_matrix):
        assert not re.search(r"[Ll]earns your words", doc)
        assert "test_corrections.py" not in doc


# --- CHANGELOG is English-only with a single open section ------------------


def test_changelog_has_no_french_markers(changelog: str):
    found = [marker for marker in FRENCH_MARKERS if marker in changelog]
    assert not found, f"French-language markers found in CHANGELOG.md: {found}"


def test_changelog_has_exactly_one_unreleased_section(changelog: str):
    assert changelog.count("## [Unreleased]") == 1

"""Doc-code parity guard tests.

Plain pytest functions reading doc files as text, so the cheapest-to-check
facts in README.md, AGENTS.md, CONTRIBUTING.md, CHANGELOG.md and the docs site
can't silently drift from the code.
"""

import html
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
DOCS_DIR = ROOT / "website" / "docs"
SCHEMA = ROOT / "docs" / "src" / "config-schema.json"
SETTINGS_RS = ROOT / "v2" / "whispy2" / "src" / "settings.rs"
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
def agents() -> str:
    return AGENTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def changelog() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config_rows() -> dict[str, str]:
    """Map each documented config key to its Default cell text (HTML-unescaped)."""
    page = (DOCS_DIR / "config.html").read_text(encoding="utf-8")
    table = re.search(r'<table id="config-reference">(.*?)</table>', page, re.DOTALL)
    assert table is not None, "config.html has no config-reference table"
    rows = {}
    for key, cells in re.findall(r'<tr id="cfg-([^"]+)">(.*?)</tr>', table.group(1), re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", cells, re.DOTALL)
        rows[key] = html.unescape(re.sub(r"</?code>", "", tds[1]))
    return rows


def _section(text: str, heading: str) -> str:
    """Return the body of the first `## <heading>` section (up to the next `## `)."""
    match = re.search(rf"^## .*{re.escape(heading)}.*$", text, re.MULTILINE)
    assert match is not None, f"section heading containing {heading!r} not found"
    start = match.end()
    next_heading = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


# --- The documented config keys are the ones Whispy reads -------------------


def test_config_schema_lists_every_key_the_app_reads(schema: dict):
    """settings.rs reads its keys with `root.get("<key>")`; the panel adds omarchy_trigger."""
    read = set(re.findall(r'root\.get\("([a-z_]+)"\)', SETTINGS_RS.read_text(encoding="utf-8")))
    assert read, "no root.get(...) key found in settings.rs"
    assert set(schema) == read | {"omarchy_trigger"}


def test_config_docs_document_the_schema(schema: dict, config_rows: dict[str, str]):
    assert set(config_rows) == set(schema)
    for key, spec in schema.items():
        assert config_rows[key] == json.dumps(spec["default"]), f"docs default for `{key}` drifted"


def test_docs_do_not_document_v1_only_config_keys(config_rows: dict[str, str]):
    for gone in ("custom_vocabulary", "pause_ms", "max_chunk_s", "min_recording_duration", "tray_icon", "model_size"):
        assert gone not in config_rows


def test_settings_defaults_match_the_schema(schema: dict):
    """`impl Default for Settings` in settings.rs states the defaults the docs show."""
    text = SETTINGS_RS.read_text(encoding="utf-8")
    block = re.search(r"impl Default for Settings \{(.*?)\n\}", text, re.DOTALL)
    assert block is not None
    body = block.group(1)
    assert f"copy_to_clipboard: {json.dumps(schema['copy_to_clipboard']['default'])}" in body
    assert f"type_while_speaking: {json.dumps(schema['type_while_speaking']['default'])}" in body
    assert schema["trigger_mode"]["default"] == "hold" and "trigger_mode: TriggerMode::Hold" in body
    assert schema["trigger"]["default"] is None and "trigger: Trigger::fn_key()" in body


# --- V1 is gone from what users read (issue #54, criterion 3) ---------------


def _user_pages() -> dict[str, str]:
    pages = {"website/index.html": (ROOT / "website" / "index.html").read_text(encoding="utf-8")}
    for page in sorted(DOCS_DIR.glob("*.html")):
        pages[f"website/docs/{page.name}"] = page.read_text(encoding="utf-8")
    return pages


@pytest.mark.parametrize(
    "phrase",
    [
        r"\bV1\b",
        r"coming (to Linux )?soon",
        r"reaches Linux",
        r"V2 reaches",
        "9090",
        "config.token",
        "make doctor",
        "install.sh",
        "custom_vocabulary",
        r"\.venv",
    ],
)
def test_site_and_docs_no_longer_mention_v1(phrase: str):
    hits = [name for name, text in _user_pages().items() if re.search(phrase, text, re.IGNORECASE)]
    assert not hits, f"{phrase!r} still appears in {hits}"


def test_readme_points_at_the_v1_tag_only_as_history(readme: str):
    assert "/tree/v1" in readme
    assert "coming to Linux" not in readme
    assert "make doctor" not in readme


def test_agents_describes_the_rust_app(agents: str):
    assert "Language:** Python 3" not in agents
    assert "Rust" in agents
    assert "localhost:9090" not in agents


# --- Test suite documentation matches the tests/ directory -----------------


def test_contributing_test_table_paths_exist(contributing: str):
    paths = re.findall(r"`(tests/[^`]+\.py)`", _section(contributing, "Running the tests"))
    assert paths, "CONTRIBUTING.md test table lists no test files"
    for path in paths:
        assert (ROOT / path).is_file(), f"CONTRIBUTING references nonexistent test file: {path}"


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


def test_docs_do_not_advertise_correction_learning(readme: str):
    """The adaptive-correction feature was removed (tracked in issue #8)."""
    assert not re.search(r"[Ll]earns your words", readme)


# --- CHANGELOG is English-only with a single open section ------------------


def test_changelog_has_no_french_markers(changelog: str):
    found = [marker for marker in FRENCH_MARKERS if marker in changelog]
    assert not found, f"French-language markers found in CHANGELOG.md: {found}"


def test_changelog_has_exactly_one_unreleased_section(changelog: str):
    assert changelog.count("## [Unreleased]") == 1

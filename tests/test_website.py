"""Structural tests for the static promotional website under ``website/``.

There is no JS/browser test harness in this project, so the high-value
regressions for a static site are validated from Python: that the page exists,
carries the brand identity and required content sections, links to the
repository, and that every locally-referenced asset actually exists on disk
(the most common static-site breakage when files are renamed or moved).
"""

import re
from pathlib import Path

import pytest

WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
INDEX = WEBSITE_DIR / "index.html"
BRAND_GREEN = "#24bf9e"
REPO_URL = "https://github.com/albrones/whispy"


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_index_exists():
    assert INDEX.is_file(), "website/index.html is missing"


def test_brand_name_present(html: str):
    assert "Whispy" in html


def test_brand_color_applied():
    css = (WEBSITE_DIR / "styles.css").read_text(encoding="utf-8")
    assert BRAND_GREEN in css, "brand green accent missing from stylesheet"


def test_links_to_repository(html: str):
    assert REPO_URL in html


@pytest.mark.parametrize("anchor", ["features", "how", "privacy", "install"])
def test_required_sections_present(html: str, anchor: str):
    assert f'id="{anchor}"' in html, f"missing required section #{anchor}"


def test_has_title_and_description(html: str):
    assert "<title>" in html and "Whispy" in html
    assert re.search(r'<meta\s+name="description"', html), "missing meta description"


def test_reduced_motion_supported():
    css = (WEBSITE_DIR / "styles.css").read_text(encoding="utf-8")
    js = (WEBSITE_DIR / "script.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css
    assert "prefers-reduced-motion" in js, "waveform animation must honor reduced motion"


def test_all_local_assets_exist(html: str):
    """Every relative href/src in the page must resolve to a file on disk."""
    refs = re.findall(r'(?:href|src)="([^"]+)"', html)
    missing = []
    for ref in refs:
        # Skip external URLs and in-page anchors.
        if ref.startswith(("http://", "https://", "//", "#", "mailto:", "data:")):
            continue
        target = (WEBSITE_DIR / ref).resolve()
        if not target.is_file():
            missing.append(ref)
    assert not missing, f"referenced local assets do not exist: {missing}"

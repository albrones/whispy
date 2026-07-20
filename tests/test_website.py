"""Structural tests for the static promotional website under ``website/``.

There is no JS/browser test harness in this project, so the high-value
regressions for a static site are validated from Python: that the page exists,
carries the brand identity and required content sections, links to the
repository, and that every locally-referenced asset actually exists on disk
(the most common static-site breakage when files are renamed or moved).
"""

import json
import re
from pathlib import Path

import pytest

WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
INDEX = WEBSITE_DIR / "index.html"
BRAND_GREEN = "#24bf9e"
REPO_URL = "https://github.com/albrones/whispy"
# Canonical host the site declares. Update alongside index.html when a custom
# domain is attached in Vercel.
CANONICAL_HOST = "whispy-dun.vercel.app"


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


def test_states_correct_license(html: str):
    """The site must state GPLv3 (the project license), never MIT."""
    assert "GPLv3" in html, "site must state the GPLv3 license"
    assert "MIT" not in html, "site must not claim an MIT license"


def test_no_sox_dependency_claim(html: str):
    """sox is no longer a dependency (sounddevice/PortAudio); the site must not
    tell users to install it."""
    assert "brew install sox" not in html
    assert "requires sox" not in html.lower()


def test_og_image_is_not_svg(html: str):
    """Open Graph / Twitter card images must be a real raster format (SVG does
    not render in social previews)."""
    og = re.search(r'property="og:image"\s+content="([^"]+)"', html)
    assert og is not None, "missing og:image"
    assert og.group(1).lower().endswith((".png", ".jpg", ".jpeg")), "og:image must be PNG/JPG, not SVG"


def test_has_canonical_link(html: str):
    """A single canonical URL on the declared host, so crawlers index one origin."""
    m = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', html)
    assert m is not None, 'missing <link rel="canonical">'
    assert CANONICAL_HOST in m.group(1), "canonical href must point at the canonical host"


def test_og_image_is_absolute(html: str):
    """Social crawlers do not resolve relative paths — og/twitter images must be
    absolute URLs on the canonical host."""
    for prop in (r'property="og:image"', r'name="twitter:image"'):
        m = re.search(prop + r'\s+content="([^"]+)"', html)
        assert m is not None, f"missing {prop} tag"
        url = m.group(1)
        assert url.startswith(("http://", "https://")), f"{prop} must be an absolute URL"
        assert CANONICAL_HOST in url, f"{prop} must be on the canonical host"


def test_softwareapplication_jsonld(html: str):
    """A parseable SoftwareApplication JSON-LD block powers Google app rich results."""
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    assert blocks, "missing JSON-LD structured data"
    apps = []
    for raw in blocks:
        data = json.loads(raw)  # must parse — invalid JSON fails the test
        if data.get("@type") == "SoftwareApplication":
            apps.append(data)
    assert apps, "no SoftwareApplication JSON-LD block found"
    app = apps[0]
    assert app.get("name")
    assert app.get("operatingSystem")
    assert str(app.get("offers", {}).get("price")) == "0", "free app must declare price 0"
    assert app.get("license"), "SoftwareApplication should declare a license"


def test_crawler_files_present():
    """robots.txt + sitemap.xml must exist and reference the canonical host."""
    robots = WEBSITE_DIR / "robots.txt"
    sitemap = WEBSITE_DIR / "sitemap.xml"
    assert robots.is_file(), "website/robots.txt is missing"
    assert sitemap.is_file(), "website/sitemap.xml is missing"
    robots_txt = robots.read_text(encoding="utf-8")
    assert "Sitemap:" in robots_txt, "robots.txt must declare a Sitemap"
    assert CANONICAL_HOST in robots_txt, "robots.txt sitemap must use the canonical host"
    assert CANONICAL_HOST in sitemap.read_text(encoding="utf-8"), "sitemap.xml must list the canonical host"


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

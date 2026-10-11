"""Guards for the generated documentation site (website/docs)."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from whispy import doctor
from whispy.core.config import CONFIG_SCHEMA

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "website" / "docs"
PAGES = ["index", "install", "troubleshooting", "config", "usage"]


def _load_generator():
    spec = importlib.util.spec_from_file_location("build_docs", REPO / "scripts" / "build_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_docs_are_fresh():
    problems = gen.check()
    assert not problems, f"{gen.STALE_MESSAGE}: {problems}"
    assert "make docs" in gen.STALE_MESSAGE


def test_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    gen.build(a)
    gen.build(b)
    assert _tree(a) == _tree(b)


def test_generated_pages_carry_notice():
    for page in PAGES:
        text = (DOCS / f"{page}.html").read_text(encoding="utf-8")
        assert "do not edit; run `make docs`" in text
        assert "\r" not in text


def _copy_src(tmp_path) -> Path:
    src = tmp_path / "src"
    shutil.copytree(gen.SRC, src)
    return src


def test_check_without_troubleshooting_entry_fails(tmp_path):
    src = _copy_src(tmp_path)
    path = src / "troubleshooting.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    victim = doctor.CHECKS[0].check_id
    for sym in data["symptoms"]:
        sym["steps"] = [s for s in sym["steps"] if s.get("check") != victim]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=victim):
        gen.build(tmp_path / "out", src_dir=src)


def test_unknown_check_id_fails(tmp_path):
    src = _copy_src(tmp_path)
    path = src / "troubleshooting.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["symptoms"][0]["steps"].append({"check": "no-such-check", "fix": {"macos": "x", "linux": "x"}})
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="no-such-check"):
        gen.build(tmp_path / "out", src_dir=src)


def test_every_check_is_reachable_with_its_name():
    text = (DOCS / "troubleshooting.html").read_text(encoding="utf-8")
    for fn in doctor.CHECKS:
        assert f'data-check="{fn.check_id}"' in text
        assert f"<summary>{fn.check_name[:1].upper() + fn.check_name[1:]}</summary>" in text
    assert "Run <code>make doctor</code> to confirm." in text


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: dict[str, list[str]] = {}
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and attrs.get("id", "").startswith("cfg-"):
            self._row = attrs["id"][4:]
            self.rows[self._row] = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self.rows[self._row].append("".join(self._cell))
            self._cell = None
        elif tag == "tr":
            self._row = None


def test_reference_table_matches_schema():
    parser = _TableParser()
    parser.feed((DOCS / "config.html").read_text(encoding="utf-8"))
    assert set(parser.rows) == set(CONFIG_SCHEMA)
    for key, spec in CONFIG_SCHEMA.items():
        assert parser.rows[key][1] == json.dumps(spec.default)


def test_embedded_schema_matches():
    text = (DOCS / "config.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="config-schema">(.*?)</script>', text, re.S)
    schema = json.loads(m.group(1).replace("<\\/", "</"))
    assert list(schema) == list(CONFIG_SCHEMA)
    consts = re.search(r'id="segmenter-constants">(.*?)</script>', text, re.S)
    assert json.loads(consts.group(1))["hard_max_factor"] == 1.5
    assert 'id="config-builder"' in text and 'id="segment-viz"' in text


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.refs.append(value)
                if tag == "link":
                    self.hrefs.append(value)


@pytest.mark.parametrize("page", PAGES)
def test_page_is_well_formed_and_links_resolve(page):
    text = (DOCS / f"{page}.html").read_text(encoding="utf-8")
    assert re.search(r"<title>[^<]+</title>", text)
    parser = _Refs()
    parser.feed(text)
    assert "../styles.css" in parser.hrefs
    for ref in parser.refs:
        if re.match(r"^(https?:|mailto:|#)", ref):
            continue
        target = (DOCS / ref.split("#")[0]).resolve()
        assert target.exists(), f"{page}: {ref} does not exist"


def test_nav_marks_current_page():
    for page in PAGES:
        text = (DOCS / f"{page}.html").read_text(encoding="utf-8")
        assert text.count('aria-current="page"') == 1
        assert f'<a href="{page}.html" aria-current="page">' in text


def test_install_has_both_os_blocks_without_js():
    text = (DOCS / "install.html").read_text(encoding="utf-8")
    assert 'data-os="macos"' in text
    assert 'data-os="linux"' in text


def test_usage_api_examples_are_authenticated():
    text = (DOCS / "usage.html").read_text(encoding="utf-8")
    assert text.count("Authorization: Bearer $(cat ~/.config/whispy/config.token)") >= 3
    assert "The port is defined near the top of <code>src/whispy/api/server.py</code>." in text

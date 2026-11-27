"""Guards for the generated documentation site (website/docs)."""

from __future__ import annotations

import html
import importlib.util
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "website" / "docs"
PAGES = ["index", "install", "troubleshooting", "config", "usage"]
CONFIG_SCHEMA = json.loads((REPO / "docs" / "src" / "config-schema.json").read_text(encoding="utf-8"))


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


def test_a_cause_without_a_fix_fails(tmp_path):
    src = _copy_src(tmp_path)
    path = src / "troubleshooting.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["symptoms"][0]["steps"].append({"title": "Broken cause"})
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="title and a fix"):
        gen.build(tmp_path / "out", src_dir=src)


def test_a_fix_for_an_os_the_symptom_lacks_fails(tmp_path):
    src = _copy_src(tmp_path)
    path = src / "troubleshooting.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    linux_only = next(sym for sym in data["symptoms"] if sym["os"] == ["linux"])
    linux_only["steps"].append({"title": "Mac cause", "fix": {"macos": "<p>x</p>"}})
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="another OS"):
        gen.build(tmp_path / "out", src_dir=src)


def test_an_unknown_config_kind_fails(tmp_path):
    src = _copy_src(tmp_path)
    path = src / "config-schema.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["trigger_mode"]["kind"] = "str_list"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        gen.build(tmp_path / "out", src_dir=src)


def test_every_cause_shows_its_title_and_fixes():
    text = (DOCS / "troubleshooting.html").read_text(encoding="utf-8")
    data = json.loads((gen.SRC / "troubleshooting.json").read_text(encoding="utf-8"))
    for sym in data["symptoms"]:
        assert f'id="{sym["id"]}"' in text
        for step in sym["steps"]:
            if "title" in step:
                assert f"<summary>{html.escape(step['title'])}</summary>" in text
    assert "make doctor" not in text


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
        assert parser.rows[key][1] == json.dumps(spec["default"])


def test_embedded_schema_matches():
    text = (DOCS / "config.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="config-schema">(.*?)</script>', text, re.S)
    schema = json.loads(m.group(1).replace("<\\/", "</"))
    assert schema == CONFIG_SCHEMA
    assert 'id="config-builder"' in text
    assert "segment-viz" not in text


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


def test_usage_documents_the_control_socket_not_an_http_api():
    text = (DOCS / "usage.html").read_text(encoding="utf-8")
    assert "whispy2 send status" in text
    assert "~/.whispy/v2/control.sock" in text
    assert "Authorization: Bearer" not in text
    assert "9090" not in text

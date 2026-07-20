"""Version-consistency guard between pyproject.toml and the py2app build spec.

`pyproject.toml`'s `[project].version` and `packaging/macos/setup_app.py`'s
`VERSION` can drift independently -- nothing else in CI or the test suite
compares them. This test runs in the default (mocked/unit) tier, so a
mismatch fails the fast job on every push/PR instead of only surfacing at
release time.
"""

import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SETUP_APP = ROOT / "packaging" / "macos" / "setup_app.py"


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def _setup_app_version() -> str:
    content = SETUP_APP.read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match, "VERSION assignment not found in packaging/macos/setup_app.py"
    return match.group(1)


def test_shipped_version_matches_setup_app():
    assert _pyproject_version() == _setup_app_version()

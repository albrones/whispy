"""Version-consistency guard between pyproject.toml and the py2app build spec.

`pyproject.toml`'s `[project].version` and `packaging/macos/setup_app.py`'s
`VERSION` can drift independently -- nothing else in CI or the test suite
compares them. This test runs in the default (mocked/unit) tier, so a
mismatch fails the fast job on every push/PR instead of only surfacing at
release time.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SETUP_APP = ROOT / "packaging" / "macos" / "setup_app.py"


def _pyproject_version() -> str:
    # Regex rather than tomllib: tomllib is stdlib only on 3.11+, and this
    # runs in the default tier down to 3.10. A single `version = "..."` line
    # is all we compare, so no TOML parser is needed.
    content = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match, "version assignment not found in pyproject.toml"
    return match.group(1)


def _setup_app_version() -> str:
    content = SETUP_APP.read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match, "VERSION assignment not found in packaging/macos/setup_app.py"
    return match.group(1)


def test_shipped_version_matches_setup_app():
    assert _pyproject_version() == _setup_app_version()

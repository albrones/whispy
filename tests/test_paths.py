"""Unit tests for daemon path resolution (pure, no rumps import)."""

import os
import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.paths import (
    DAEMON_SCRIPT_NAME,
    daemon_script_exists,
    resolve_app_bundle,
    resolve_daemon_script,
)


class TestResolveDaemonScript:
    def test_resolves_to_daemon_filename(self):
        assert resolve_daemon_script().name == DAEMON_SCRIPT_NAME == "whispy_daemon.py"

    def test_resolves_to_project_root(self):
        # Project root is three levels above the package source dir.
        expected_root = Path(__file__).parent.parent.resolve()
        assert resolve_daemon_script() == expected_root / "whispy_daemon.py"

    def test_resolution_is_independent_of_cwd(self, tmp_path):
        original = resolve_daemon_script()
        prev = os.getcwd()
        try:
            os.chdir(tmp_path)
            assert resolve_daemon_script() == original
        finally:
            os.chdir(prev)

    def test_daemon_script_exists_in_repo(self):
        # In the dev checkout the daemon entry point is present.
        assert daemon_script_exists() is True


class TestDaemonScriptExists:
    def test_true_for_existing_path(self, tmp_path):
        f = tmp_path / "whispy_daemon.py"
        f.write_text("# stub")
        assert daemon_script_exists(f) is True

    def test_false_for_missing_path(self, tmp_path):
        assert daemon_script_exists(tmp_path / "nope.py") is False


class TestResolveAppBundle:
    def test_detects_bundle_from_executable(self):
        exe = "/Applications/Whispy.app/Contents/MacOS/python"
        assert resolve_app_bundle(exe) == Path("/Applications/Whispy.app")

    def test_returns_nearest_app_ancestor(self):
        exe = "/Users/me/Builds/Whispy.app/Contents/MacOS/Whispy"
        assert resolve_app_bundle(exe) == Path("/Users/me/Builds/Whispy.app")

    def test_none_for_plain_venv_executable(self):
        assert resolve_app_bundle("/Users/me/proj/.venv/bin/python3") is None

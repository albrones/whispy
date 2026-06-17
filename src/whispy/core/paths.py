"""Pure path resolution helpers.

Extracted from the menu bar UI so the daemon entry-point resolution is
unit-testable without importing rumps. This module sits at
``src/whispy/core/paths.py``; the project root is three directories up from the
package (``core`` -> ``whispy`` -> ``src`` -> project root).
"""

from pathlib import Path

# Project root: parents[3] of this file (core -> whispy -> src -> <root>).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Daemon entry-point filename at the project root.
DAEMON_SCRIPT_NAME = "whispy_daemon.py"


def resolve_daemon_script() -> Path:
    """Return the path to the daemon entry point at the project root.

    Independent of the current working directory — resolution is anchored to
    this module's location, not to where the process was launched.
    """
    return _PROJECT_ROOT / DAEMON_SCRIPT_NAME


def daemon_script_exists(path: Path | None = None) -> bool:
    """Return whether the daemon entry-point script exists.

    Defaults to the resolved daemon path; accepts an explicit path for testing.
    """
    target = path if path is not None else resolve_daemon_script()
    return target.exists()

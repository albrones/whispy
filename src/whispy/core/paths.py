"""Pure path resolution helpers.

Extracted from the menu bar UI so the daemon entry-point resolution is
unit-testable without importing rumps. This module sits at
``src/whispy/core/paths.py``; the project root is three directories up from the
package (``core`` -> ``whispy`` -> ``src`` -> project root).
"""

import os
import sys
from pathlib import Path

# Project root: parents[3] of this file (core -> whispy -> src -> <root>).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Daemon entry-point filename at the project root.
DAEMON_SCRIPT_NAME = "whispy_daemon.py"


def transcribe_allow_dir() -> Path:
    """Return the only directory ``POST /transcribe-file`` may read from.

    The endpoint is a deterministic validation seam (transcribe a known WAV with
    the current config). Restricting it to an allow-listed directory removes the
    arbitrary-filesystem-read / existence-oracle that an unauthenticated caller
    could otherwise abuse. Defaults to the committed audio fixtures; overridable
    via ``WHISPY_TRANSCRIBE_DIR`` for tests or alternate fixture locations.
    """
    override = os.environ.get("WHISPY_TRANSCRIBE_DIR")
    base = Path(override) if override else _PROJECT_ROOT / "tests" / "fixtures" / "audio"
    return base.resolve()


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


def resolve_app_bundle(executable: str | None = None) -> Path | None:
    """Return the ``.app`` bundle path when running inside one, else ``None``.

    A py2app bundle runs from ``…/Whispy.app/Contents/MacOS/python``; walk the
    executable's parents for the nearest ancestor ending in ``.app``. Returns
    ``None`` in a normal source-tree/venv run. ``executable`` is injectable so
    the resolution is unit-testable.
    """
    exe = Path(executable if executable is not None else sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None

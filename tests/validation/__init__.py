"""Whispy release-validation harness.

The `make validate` / `/validate` system: preflight (doctor) → live-drive (real
daemon over HTTP) → operator checklist, with a three-state reporting contract
(PASS / FAIL / UNVERIFIED) so a green result can never mean "nothing ran".

See `FEATURE_MATRIX.md` (the single source of truth) and the `release-validation`
capability spec under `openspec/specs/`.
"""

import sys as _sys
from pathlib import Path as _Path

# Make `whispy` (src layout) and the repo root importable when this package is
# run via `python -m tests.validation.run` outside pytest (pytest's `pythonpath`
# setting does not apply there).
_root = _Path(__file__).resolve().parents[2]
for _p in (str(_root), str(_root / "src")):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

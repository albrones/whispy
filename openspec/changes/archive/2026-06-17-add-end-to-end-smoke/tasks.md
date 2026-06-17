## 1. Test scaffolding

- [x] 1.1 Create `tests/test_e2e_smoke.py`, `pytestmark = pytest.mark.macos`; module-level skip when `sox`/`osascript`/`pbpaste` are unavailable
- [x] 1.2 Add a module docstring documenting the operator manual flow (hold Fn → speak → text appears) that this layer does NOT automate

## 2. Real audio capture

- [x] 2.1 Drive `AudioEngine.start()` / `stop()` against the default device for a short interval (patch `RECORDING_PATH` to a tmp file)
- [x] 2.2 Assert the output is a valid WAV (readable via `wave`), 16 kHz mono, size above the readiness threshold; skip on `sox`/device error

## 3. Real osascript clipboard seam

- [x] 3.1 Set a unique token on the clipboard via real `osascript`, read it back with `pbpaste`, assert equality
- [x] 3.2 Note in the test that the Cmd+V-into-focused-field paste is the operator boundary (not automated)

## 4. Live event tap (subprocess)

- [x] 4.1 Spawn a `python -c` subprocess (PYTHONPATH=src, no conftest) that starts a real `EventTapListener` and prints `ACTIVE`/`INACTIVE`
- [x] 4.2 Assert `ACTIVE`; skip with an Input-Monitoring message on `INACTIVE` or non-zero exit

## 5. Verify + spec sync

- [x] 5.1 Run `pytest -m macos tests/test_e2e_smoke.py` locally; confirm pass-or-clean-skip per seam (report which seams ran vs skipped)
- [x] 5.2 Confirm default `pytest` still excludes them (378 passed, deselected count grows)
- [x] 5.3 Apply the `end-to-end-smoke` spec into `openspec/specs/end-to-end-smoke/spec.md`

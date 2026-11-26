## 1. V2 socket

- [x] 1.1 `level` in `status`; `last` request; text in memory only (`Live`)
- [x] 1.2 `whispy2 send <request>` client, exit codes 0 / 1 / 2
- [x] 1.3 Unit tests (protocol, controller: level while recording, last text)

## 2. Omarchy

- [x] 2.1 `omarchy-dictation-whispy` on `whispy2 send`; `trigger` saves with `jq`
- [x] 2.2 `Service.qml` on Quickshell's `Socket`; `Model.js` phases from V2's status
- [x] 2.3 Panel: Copy to clipboard, Start at login, Start Whispy, power switch removed
- [x] 2.4 Tests: `test_omarchy_adapter.py`, `test_omarchy_panel_model.py`

## 3. Proof and docs

- [x] 3.1 `linux-e2e/omarchy.sh`: keys, panel under Quickshell, no TCP listener
- [x] 3.2 Specs, `v2/README.md`, user docs (`make docs`)

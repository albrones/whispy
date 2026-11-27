## 1. Install

- [x] 1.1 `packaging/linux/reinstall.sh`: build, retire V1, install, unit, wait; `--uninstall`
- [x] 1.2 `scripts/bootstrap.sh`: Linux build packages, Rust, cmake; uninstall
- [x] 1.3 Makefile: `reinstall`, `uninstall` per OS

## 2. Omarchy panel

- [x] 2.1 Power switch, Start Whispy, Start at login on `whispy2.service`

## 3. V1 removal

- [x] 3.1 Tag `v1` on the last V1 commit of `main`
- [x] 3.2 Delete V1 code, packaging and tests; move the signing script and icon
- [x] 3.3 Python tooling without the `whispy` package; CI jobs

## 4. Site, docs, proof

- [x] 4.1 `website/index.html`, `docs/src/` (V2 only), README, CONTRIBUTING, AGENTS
- [x] 4.2 Tests: `test_install_scripts.py` (stubbed run), docs and panel guards
- [x] 4.3 `v2/whispy2/linux-e2e/install.sh`

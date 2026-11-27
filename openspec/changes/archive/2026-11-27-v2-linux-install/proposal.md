## Why

Card 3/3 of the Linux switch to V2 (albrones/whispy#54). With the app (#59)
and Omarchy (#61) on V2, the install command must install V2 on Linux and the
Python V1 must leave the repository, the site and the docs.

## What Changes

- **Install**: `scripts/bootstrap.sh` on Linux installs the build packages
  (apt, dnf, pacman), Rust and cmake if needed, then
  `packaging/linux/reinstall.sh` (also `make reinstall`) builds `whispy2`,
  replaces a V1 install, installs `~/.local/bin/whispy2` and runs it as the
  `systemd --user` unit `whispy2.service`.
- **Omarchy panel**: the power switch, « Start Whispy » and Start at login come
  back (removed in 2/3), on `whispy2.service` (Alexis' choice).
- **V1 removed** after the tag `v1`: `src/`, `whispy_daemon.py`, `install.sh`,
  `packaging/macos/` (the signing script and the icon moved to
  `packaging/macos-v2/`), V1's tests and validation harness. Python stays as
  repository tooling only (`scripts/release.py`, `scripts/build_docs.py`, the
  pytest guards).
- **Site and docs**: V2 only; the docs generator no longer imports V1 (config
  schema and troubleshooting tree are data files in `docs/src/`).
- Not ported, as decided at framing: `custom_vocabulary`, `POST /transcribe`,
  `GET /level`.

## Impact

- Specs: new `v2-linux-install`; `linux-support` (purpose, bar widget).
- CI: V1's Python jobs replaced by a lint and a tooling job.
- Proof: `v2/whispy2/linux-e2e/install.sh`.

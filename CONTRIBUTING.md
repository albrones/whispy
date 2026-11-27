# Contributing to Whispy

Thanks for your interest in improving Whispy! This document explains how to set up a
development environment, run the tests, and submit changes.

Whispy is a Rust app (`v2/`) for **macOS and Linux (X11 and Wayland)**. The repository
also holds its packaging (`packaging/`), the installer (`scripts/bootstrap.sh`), the
website (`website/`) and a little Python tooling (`scripts/release.py`,
`scripts/build_docs.py`) with the pytest guards of the website, docs and install scripts.

## Development setup

```bash
git clone https://github.com/albrones/whispy.git
cd whispy
```

You need Rust (<https://rustup.rs>) and cmake. On Linux, also the build libraries the
installer lists (a C/C++ toolchain, clang, pkg-config, the ALSA and xkbcommon headers:
see the [install guide](https://whispy-dun.vercel.app/docs/install.html)). For the
tooling tests, `make install` creates a `.venv` with pytest and ruff.

## Trying a change in the real app

```bash
make reinstall    # rebuild, replace the installed Whispy, relaunch it, wait for its socket
```

On macOS it rebuilds and signs `Whispy V2.app` and replaces `/Applications/Whispy V2.app`;
on Linux it rebuilds `whispy2`, replaces `~/.local/bin/whispy2` and restarts the
`whispy2.service` unit. A plain relaunch reruns the old build. For a quick loop,
`cd v2 && cargo run --release --bin whispy2` runs it in the foreground (stop the
installed one first: the control socket is a single-instance lock).

## Running the tests

```bash
make test         # cargo test (v2/) and the tooling tests (pytest)
make lint         # cargo fmt --check, clippy -D warnings, ruff
```

The app's own tests, end-to-end checks and bench are described in
[`v2/README.md`](v2/README.md). The pytest files under `tests/` guard the repository
around it:

| File | Scope |
|------|-------|
| `tests/test_release.py` | `scripts/release.py`: the next version from the conventional commits |
| `tests/test_install_scripts.py` | `scripts/bootstrap.sh`, `packaging/linux/reinstall.sh`, the macOS packaging and the Makefile |
| `tests/test_omarchy_adapter.py` | the Omarchy dictation backend (`packaging/omarchy/omarchy-dictation-whispy`) |
| `tests/test_omarchy_panel_model.py` | the Omarchy bar panel's model and its service control |
| `tests/test_website.py` | the landing page |
| `tests/test_docs.py` | README, CHANGELOG and docs facts that must not drift |
| `tests/test_docs_site.py` | generated docs freshness, determinism, troubleshooting and config reference |
| `tests/test_docs_widgets.py` | the config builder's logic (through node when available) |

## Regenerating the docs

The user docs (install, troubleshooting, configuration, usage) live as sources in
`docs/src/` and are published from the generated pages in `website/docs/`.

```bash
make docs    # regenerate website/docs/ from docs/src/
```

Commit the regenerated `website/docs/` together with your change, and never edit
`website/docs/` by hand. `tests/test_docs_site.py` fails when the generated pages are stale.

## Code style

`cargo fmt` and `cargo clippy -- -D warnings` for Rust; [Ruff](https://docs.astral.sh/ruff/)
for the Python tooling. `make lint` runs all of them, `make format` formats.

## Submitting changes

1. Fork the repo and create a feature branch (`feat/...` or `fix/...`).
2. Add at least one test that covers your change.
3. Make sure `make lint` and `make test` pass locally.
4. Open a pull request describing **what** changed and **why**. Reference any related
   issue. Commit messages follow Conventional Commits: on `main`, a `feat` or `fix`
   publishes a new version.

By contributing, you agree that your contributions are licensed under the project's
GPLv3 license (see [LICENSE](LICENSE)).

## Reporting bugs and requesting features

Use the GitHub issue templates. For bugs, include your OS (macOS version, or Linux
distro + X11/Wayland) and the relevant lines from `~/.whispy/v2/whispy2.log`.

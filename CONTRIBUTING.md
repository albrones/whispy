# Contributing to Whispy

Thanks for your interest in improving Whispy! This document explains how to set up a
development environment, run the test suite, and submit changes.

Whispy currently targets **macOS only**. Most of the codebase runs and tests cleanly on
any platform (the macOS-only dependencies are mocked in the test suite), but the app
itself requires macOS to run end to end.

## Development setup

```bash
git clone https://github.com/albrones/whispy.git
cd whispy

# Create a virtual environment and install the package in editable mode with dev deps
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e ".[dev]"

# Runtime audio dependency (macOS)
brew install sox
```

## Running the tests

```bash
./.venv/bin/pytest                 # full suite
./.venv/bin/pytest -v              # verbose
./.venv/bin/pytest --cov=src/whispy --cov-report=term-missing   # with coverage
```

The macOS-only dependencies (`Quartz`, `rumps`) are mocked in `tests/conftest.py`, so the
suite runs on non-macOS machines and in CI.

## Code style

Whispy uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
./.venv/bin/ruff check .           # lint
./.venv/bin/ruff format .          # auto-format
./.venv/bin/ruff format --check .  # verify formatting (what CI runs)
```

If a `Makefile` is present, `make lint`, `make format`, and `make test` wrap these
commands.

## Submitting changes

1. Fork the repo and create a feature branch (`feat/...` or `fix/...`).
2. Add at least one test that covers your change.
3. Make sure `ruff check .`, `ruff format --check .`, and `pytest` all pass locally.
4. Open a pull request describing **what** changed and **why**. Reference any related
   issue.

By contributing, you agree that your contributions are licensed under the project's
GPLv3 license (see [LICENSE](LICENSE)).

## Reporting bugs and requesting features

Use the GitHub issue templates. For bugs, include your macOS version, the model in use,
and the relevant lines from `~/.whispy.log` / `~/.whispy-error.log`.

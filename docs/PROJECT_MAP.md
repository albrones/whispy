whispy/PROJECT_MAP.md
# Project Map — whispy

This file provides a technical overview of the `whispy` codebase.  
It is designed to help AI agents and developers quickly understand the project structure, main components, and navigation strategies.

---

## Directory Structure

- `whispy/`
  - `.gitignore` — Git ignore rules.
  - `LICENSE` — Project license.
  - `README.md` — High-level project introduction and usage instructions.
  - `whispy_daemon.py` — Main entry point for the application.
  - `src/whispy/` — Python package:
    - `core/` — Engine, state machine, audio engine, config
    - `hardware/` — Event tap (Fn key), text injection
    - `ui/` — Menu bar app, indicator windows, audio level monitor
      - `menu_theme.py` — Brand-accent menu styling (green dot/header/checks via
        attributed titles). **macOS-only**: the Linux tray (pystray) renders
        plain text labels and has no styling equivalent.
    - `api/` — HTTP API server
  - `FEATURE_MATRIX.md` — Single source of truth: every user-facing feature →
    coverage tier → how it is verified. Edited on every fix/feature (see its header).
  - `tests/validation/` — Release-validation system behind `make validate`:
    `outcomes.py` (PASS/FAIL/UNVERIFIED contract), `matrix.py` (parse/lint the
    feature matrix), `preflight.py` (doctor wrapper), `harness.py` (boot the real
    headless daemon and drive it over HTTP), `operator.py` (human checklist),
    `run.py` (orchestrator). `whispy_daemon.py --headless` boots engine + HTTP
    without the tray for the harness.
  - `generate_icons.py` — Script for generating icons.
  - `install.sh` — Shell script for installing dependencies and setting up the environment.
  - `icons/` — Directory containing icon assets (generated or used by the project).
  - `.venv/` — Local Python virtual environment (should be ignored by version control).

---

## Main Concepts

- **Agents**  
  Autonomous or semi-autonomous components responsible for specific tasks, logic, or interactions.  
  See `AGENTS.md` for design principles and implementation guidelines.

- **Icons**  
  All icon assets are managed in the `icons/` directory and can be generated or updated using `generate_icons.py`.

---

## Entry Points

- **Application Start:**  
  Run the project via `whispy_daemon.py`.

- **Icon Generation:**  
  Use `generate_icons.py` to (re)generate icon assets.

- **Installation:**  
  Use `install.sh` to set up the environment and install dependencies.

---

## Conventions

- All main Python scripts are located at the root of the `whispy/` directory.
- The Python virtual environment is local (`.venv/`).
- Asset files (icons) are stored in the `icons/` directory.
- Documentation files (`README.md`, `AGENTS.md`, `PROJECT_MAP.md`) are at the root for easy access.

---

## Dependencies

- Dependencies and setup instructions are managed via `install.sh`.
- The project uses a local Python virtual environment (`.venv/`).

---

## Navigation Tips

- **Start with `README.md`** for a high-level overview and basic usage.
- **Consult `AGENTS.md`** for understanding agent architecture and extension.
|- **Check `src/whispy/core/engine.py`** for the main application logic.
- **Use `generate_icons.py` and `icons/`** for anything related to icon management.
- **Refer to this `PROJECT_MAP.md`** for a quick technical orientation.

---

## Update Policy

This file should be updated whenever:
- New main scripts or directories are added.
- The project structure changes.
- Key concepts or conventions evolve.

---

## Last Updated

<!-- Please update this section with the date of the last major change -->
2024-06-07

---
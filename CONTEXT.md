whispy/CONTEXT.md
# Project Context Overview

This file provides a technical map of the `whispy` codebase to help AI agents and developers quickly understand the project structure, main components, and navigation tips. It is designed to accelerate onboarding and enable efficient code navigation and reasoning.

---

## Directory Structure

- `/whispy/`
  - `README.md` — Project introduction, high-level overview, and basic usage instructions.
  - `wispy.py` — Main entry point for the application.
  - `generate_icons.py` — Script for generating and managing icon assets.
  - `icons/` — Directory containing all icon assets used by the project.
  - `.venv/` — Python virtual environment (should be ignored by tools and version control).
  - `install.sh` — Shell script for installing dependencies and setting up the environment.
  - `AGENTS.md` — Design and best practices for implementing agents in the project.

---

## Main Concepts

- **Agents**: Autonomous or semi-autonomous components responsible for specific tasks, encapsulating logic, state, and communication. See `AGENTS.md` for design details and extension guidelines.
- **Icons**: All icon assets are managed in the `icons/` directory and generated via `generate_icons.py`.
- **Scripts**: Utility scripts (such as `generate_icons.py`) are placed at the project root for easy access.

---

## Entry Points

- **Main Application**: Run the project via `wispy.py`.
- **Icon Generation**: Use `generate_icons.py` to update or generate icon assets.

---

## Conventions

- All core Python scripts are located in the project root.
- The Python virtual environment is local (`.venv/`) and should not be committed.
- Documentation files (`README.md`, `AGENTS.md`, `CONTEXT.md`) are maintained at the root for easy discovery.
- Asset directories (such as `icons/`) are grouped by type.

---

## Dependencies

- All dependencies and setup instructions are managed via `install.sh`.
- The project uses a Python virtual environment for dependency isolation.

---

## Navigation Tips

- **Start with `README.md`** for a high-level introduction and usage instructions.
- **Consult `AGENTS.md`** for agent architecture, responsibilities, and extension practices.
- **Refer to `CONTEXT.md`** (this file) for a technical overview and navigation guidance.
- **Explore `wispy.py`** for the main application logic and entry point.
- **Check `generate_icons.py` and `icons/`** for asset management.

---

## Maintenance

- Keep this file (`CONTEXT.md`) up to date with any significant changes to the project structure, main files, or conventions.
- Update `AGENTS.md` when agent-related design or best practices evolve.
- Ensure `README.md` reflects any changes in project usage or high-level goals.

---

## For AI Agents

- Use this file as your primary source for understanding the project layout and main components.
- Prioritize files and directories listed here when searching for relevant code or documentation.
- If you make structural changes to the project, update this file to reflect the new organization.

---
# Agents

This document provides high-signal context for agents working in the `whispy` repository.

---

## 🔁 Automatic Skill Triggers

### 🛑 MANDATORY POST-ACTION: research-log (Always Active)

**The `research-log` skill is a core, always-active behavior.**
**BEFORE** you send any text reply to the user, ask yourself: *Did I use a tool, edit a file, or run a command in this turn?*
- If **NO**: Proceed normally.
- If **YES**: You are STRICTLY FORBIDDEN to answer the user until you have updated the session log.
  1. Read `.agents/skills/research-log/SKILL.md` (if you don't remember the exact format, triggers, wrap-up rules, and Linear MCP integration steps). All logic and conditions are centralized there. Do not guess the format.
  2. Perform the required tool calls to append the log and sync with Linear.
  3. Only AFTER these tools succeed, you may reply to the user.

---

## 🤖 Delegation & Model Choice (Always Active)

Systematically delegate well-scoped subtasks to subagents running the cheapest model adequate for the action, instead of doing everything in the main conversation — this avoids wasting tokens on a model that is over- or under-suited to the task:

- **Mechanical execution** (running installers, long commands, file sweeps, digesting verbose logs): haiku or sonnet subagent.
- **Well-specified implementation** from a precise brief (file paths, expected behavior, tests to run): sonnet subagent, parallelized on disjoint files when possible.
- **Design, review, reconciliation, and final triage**: stay in the main conversation (main model).

The main thread orchestrates and reviews; subagents execute and report.

## 🛠️ Core Tech Stack & Environment
- **Platform:** macOS (Apple Silicon/Intel) and Linux (X11 and Wayland sessions).
- **Language:** Rust (`v2/`: `whispy-core` the engines and pipeline, `whispy2` the app, `banc` the bench). The Python app (V1) is gone; its last state is the git tag `v1`. Python remains only as repository tooling: `scripts/release.py`, `scripts/build_docs.py` and the pytest guards in `tests/` (dependencies in `requirements-dev.txt`, `make install`).
- **Key Dependencies:** ONNX Runtime (`ort`, Parakeet TDT 0.6b v3 int8), whisper.cpp (`whisper-rs`, whisper small fallback, needs cmake), `cpal` (microphone). macOS: `objc2` (menu bar, pill, SMAppService), `core-graphics` (Fn event tap). Linux: `x11rb` (XInput 2 trigger), `enigo` (XTest / virtual keyboard typing), `ksni` (tray).

## 🚀 Operational Commands
- **Install:** `scripts/bootstrap.sh` (the one-liner) installs the toolchain and builds Whispy. macOS: `Whispy V2.app` in `/Applications`, autostart through its in-app "Start at login" (SMAppService). Linux: `~/.local/bin/whispy2` run by the `systemd --user` unit `whispy2.service`.
- **After a code change:** `make reinstall` — macOS: `packaging/macos-v2/reinstall.sh` (rebuild, sign, replace `/Applications/Whispy V2.app`, relaunch); Linux: `packaging/linux/reinstall.sh` (rebuild, replace `~/.local/bin/whispy2`, restart the unit). Both wait until the control socket answers. A bare relaunch reruns the installed build.
  ```bash
  make reinstall
  ```
- **Tests and lint:** `make test` (`cargo test` + pytest), `make lint` (fmt, clippy `-D warnings`, ruff).
- **Live Logs:** `tail -f ~/.whispy/v2/whispy2.log` (Linux also: `journalctl --user -u whispy2 -f`).
- **Control socket** (`~/.whispy/v2/control.sock`, no network port, no token): `whispy2 send status`, `start`, `stop`, `toggle`, `last`.

## 🏗️ Architecture & Workflow
- **The app (`v2/whispy2`):** one binary per platform, with a pure, unit-tested state machine (`machine.rs`) and a platform layer: `src/mac/` (menu bar, pill, event tap, paste through System Events) and `src/linux/` (X11 trigger, tray, typing, notifications).
  - **Trigger:** macOS listens to Fn (or Right Command, Right Option, F13) through a listen-only event tap (**Input Monitoring**). Linux X11 listens to Right Ctrl through XInput 2 raw events, without grabbing it. Under Wayland there is no in-process listener: the compositor binding (Omarchy: `packaging/omarchy/omarchy-dictation-whispy`) calls `whispy2 send start|stop|toggle`.
  - **Transcription:** `whispy-core` (Parakeet, then whisper small when Parakeet hears nothing; gates for silence and noise; French numbers in digits).
  - **Text insertion:** macOS pastes through the clipboard (⌘V by System Events) or types (`keystroke`), which needs **Accessibility**. Linux always types with `enigo`.
  - **UI:** macOS menu bar and pill; Linux X11 tray icon; Omarchy bar panel (`packaging/omarchy/whispy-panel/`, Quickshell) reading the control socket and driving the `whispy2.service` unit.
- **Permissions (Critical):** macOS needs **Microphone**, **Accessibility** and **Input Monitoring** for `Whispy V2`. Linux has no permission prompts.

## 📝 Development Conventions
- **Config:** `~/.config/whispy/config.json` (keys: `copy_to_clipboard`, `trigger_mode`, `trigger`, `type_while_speaking`, `omarchy_trigger`); every other key is kept as found.
- **Language:** All code, documentation, and UI strings must be in English.
- **Keep the website in sync:** any user-facing change (new feature, changed install flow, renamed setting, dropped option) MUST update `website/index.html` in the same change — install commands, feature cards, and the menu-bar demo. `tests/test_website.py` guards some of this; treat it as a floor, not the whole job. User docs live in `docs/src/` and must be regenerated with `make docs` (commit `website/docs/`); `tests/test_docs_site.py` fails on stale output.
- **Releases:** every `feat` or `fix` merged on `main` publishes a version (`.github/workflows/release.yml`, `scripts/release.py`).

**Language Policy**

All documentation, code comments, and user-facing messages in the codebase must be written in English. Communication between contributors (e.g., in issues, pull requests, or chat) can be in any language, but all code and documentation must remain in English.

---

## 💡 High-Signal Context for Agents

- **Permissions are Key:** On macOS, if the trigger doesn't record or text isn't typed, check **Input Monitoring** and **Accessibility** for `Whispy V2` in System Settings; the menu names a missing one.
- **Linux sessions:** X11 needs a display reachable from the `systemd --user` unit (`systemctl --user import-environment DISPLAY XAUTHORITY`); Wayland needs a compositor key binding. The end-to-end checks run in Docker: `v2/whispy2/linux-e2e/run.sh <models-dir>`.
- **Never block the event tap callback** (macOS): heavy work goes to the controller thread.
- More in [`v2/README.md`](v2/README.md).

---

## What is an Agent?

An **agent** is an autonomous or semi-autonomous component designed to perform specific tasks, make decisions, or interact with other parts of the system. Agents can encapsulate logic, maintain state, and communicate with other agents or system components.

---

## Agent Responsibilities

- **Task Execution:** Agents are responsible for carrying out well-defined tasks, such as data processing, monitoring, or user interaction.
- **Autonomy:** Agents can operate independently, making decisions based on their internal logic and the data they receive.
- **Communication:** Agents may communicate with other agents or system components using defined protocols or interfaces.
- **State Management:** Agents can maintain their own state, allowing them to track progress, remember context, or adapt behavior over time.

---

## Agent Structure

A typical agent in `whispy` may include:

- **Initialization:** Setup of internal state, configuration, and dependencies.
- **Main Loop or Event Handler:** Core logic for processing tasks or responding to events.
- **Interfaces:** Methods or APIs for communication with other agents or system components.
- **Error Handling:** Mechanisms for dealing with failures or unexpected situations.

---

## Example Agent Lifecycle

1. **Creation:** The agent is instantiated and initialized.
2. **Activation:** The agent begins its main loop or subscribes to events.
3. **Operation:** The agent performs its designated tasks, possibly interacting with other agents.
4. **Termination:** The agent gracefully shuts down, releasing resources and saving state if necessary.

---

## Best Practices

- **Single Responsibility:** Each agent should have a clear, focused purpose.
- **Loose Coupling:** Minimize dependencies between agents to enhance modularity and maintainability.
- **Clear Interfaces:** Define explicit methods or APIs for agent communication.
- **Robustness:** Implement error handling and recovery strategies.

---

## Extending Agents

To add a new agent:

1. Define the agent’s purpose and responsibilities.
2. Implement the agent’s logic, adhering to the structure and best practices outlined above.
3. Register or integrate the agent with the rest of the system as needed.
4. Document the agent’s behavior and interfaces.

---

## Skills

> **Auto-discovery rule:** At the start of every session, scan the `.agents/skills/` folder (gitignored — local only, not versioned). For each subdirectory found, read its `SKILL.md` file and **automatically apply** the skill without waiting for user instruction.

The `.agents/skills/` folder lives at the root of the repository and is excluded from version control (see `.gitignore`). This is intentional: skills are personal, local extensions that each developer manages independently.

### How to load skills

1. At session start, check if the `.agents/skills/` directory exists.
2. If it does, list all subdirectories (each one is a skill).
3. For each skill directory, read `.agents/skills/<skill-name>/SKILL.md`.
4. Parse the YAML frontmatter. If `trigger: always` is present, load the skill unconditionally. Otherwise, check if the user's prompt matches the keyword triggers in the `description` field.
5. Parse the skill instructions and apply them immediately and silently — no announcement needed.
6. Skills remain active for the entire session unless the user says otherwise.

### Currently documented skills

| Skill | Location | Description |
|-------|----------|-------------|
| `research-log` | `.agents/skills/research-log/SKILL.md` | Live per-turn session journal. Trigger: always. Auto-appends a log entry after every action turn. |

> If `.agents/skills/` does not exist or is empty, proceed normally — no skills are active.

---

## Conclusion

Agents are a powerful abstraction for building modular, maintainable, and scalable systems. By following the guidelines in this document, you can design and implement effective agents within the `whispy` project.

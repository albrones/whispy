# Agents

This document provides high-signal context for agents working in the `whispy` repository.

## 🛠️ Core Tech Stack & Environment
- **Platform:** macOS (Apple Silicon/Intel) only.
- **Language:** Python 3.
- **Key Dependencies:** `faster-whisper`, `rumps` (menu bar), `sox` (audio recording), `pyobjc-framework-Quartz` (Fn key detection via CGEventTap).
- **Environment:** Uses a Python virtual environment (`.venv`).

## 🚀 Operational Commands
- **Install/Setup:** `./install.sh` (manages venv, dependencies, and LaunchAgent).
- **Manual Restart:** 
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.whispy.plist
  launchctl load ~/Library/LaunchAgents/com.whispy.plist
  ```
- **Live Logs:** `tail -f ~/.whispy.log ~/.whispy-error.log`
- **API Interaction:** 
  - `curl http://localhost:9090/status` (Check daemon status)
  - `curl -X POST http://localhost:9090/start` (Manual start)
  - `curl -X POST http://localhost:9090/stop` (Manual stop)

## 🏗️ Architecture & Workflow
- **The Daemon:** The application runs as a background `LaunchAgent`. It consists of:
  - **Fn Key Listener:** Uses `CGEventTap` to detect the Fn key. Requires **Input Monitoring** permissions.
  - **Recording:** Uses `sox` to record audio to a temporary file (`/tmp/whispy.wav`).
  - **Transcription:** Uses `faster-whisper` for local inference.
  - **Text Injection:** Uses `osascript` to simulate keystrokes or paste via clipboard. Requires **Accessibility** permissions.
  - **UI:** A `rumps`-based menu bar application.
- **Permissions (Critical):** 
  - **Microphone:** Required for recording.
  - **Accessibility:** Required to type text into active fields via `osascript`.
  - **Input Monitoring:** Required for the Fn key listener (`CGEventTap`).

## 📝 Development Conventions
- **Config:** Stored in `~/.config/whispy/config.json`.
- **Logging:** Logs are written to `~/.whispy.log` and `~/.whispy-error.log`.
- **Language:** All code, documentation, and UI strings must be in English (though the current UI has some French).
- **Testing:** No dedicated test suite is present in the root; verification is primarily manual via the daemon or API.

**Language Policy**

All documentation, code comments, and user-facing messages in the codebase must be written in English. Communication between contributors (e.g., in issues, pull requests, or chat) can be in any language, but all code and documentation must remain in English.

---

## 💡 High-Signal Context for Agents

### 🛠️ Environment & Permissions
- **macOS Specific:** This project relies heavily on macOS-specific libraries (`pyobjc`, `rumps`, `osascript`).
- **Permissions are Key:** If the Fn key doesn't trigger recording or text isn't typed, check **Input Monitoring** and **Accessibility** permissions in System Settings.
- **Python Interpreter:** The daemon uses the `.venv/bin/python3` interpreter. Ensure permissions are granted to this specific executable if required.

### 🏗️ Architecture
- **Single File Core:** The main logic resides in `whispy.py`. It handles the UI, HTTP server, and background tasks (recording/transcription).
- **Concurrency:** Uses `threading` for the HTTP server, model loading, and transcription workers.
- **State Management:** A global `state` object (`DictationState`) manages recording, transcription, and model status across threads.

### 🚀 Operational Commands
- **Manual Restart:** Use `launchctl` commands to reload the daemon after code changes or permission updates.
- **Model Swapping:** Changing `model_size` in config triggers an asynchronous model reload.
- **Logging:** Always check `~/.whispy.log` and `~/.whispy-error.log` for debugging.

### 📝 Development Guidelines
- **English Only:** All code, comments, and UI strings must be in English.
- **No Tests:** There is no automated test suite. Verification is manual via the UI or API.
- **Avoid Breaking the Loop:** The `_fn_event_callback` must be non-blocking. Use threads or async processes for heavy tasks like transcription.


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

## Conclusion

Agents are a powerful abstraction for building modular, maintainable, and scalable systems. By following the guidelines in this document, you can design and implement effective agents within the `whispy` project.

---
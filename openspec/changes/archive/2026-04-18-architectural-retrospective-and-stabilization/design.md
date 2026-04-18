## Context

The current project is a single-file Python application (`whispy.py`) that manages hardware interaction (Fn key), audio recording, transcription, and UI (menu bar) within a single process. While functional, this "monolithic" approach leads to tight coupling between the UI and core logic, making it difficult to manage concurrency (threading) and state transitions reliably. The "vibecoding" approach has resulted in a system where the logic is scattered, making it prone to race conditions and difficult to test or extend.

## Goals / Non-Goals

**Goals:**
- **Decoupling**: Separate the core engine (recording/transcription) from the UI and external interfaces.
- **State Machine Formalization**: Implement a robust, thread-safe state machine to manage the lifecycle of recording and transcription.
- **Modularity**: Transition from a single file to a structured, multi-module architecture.
- **Reliability**: Eliminate race conditions and ensure predictable behavior during hardware events (Fn key) and user interactions.

**Non-Goals:**
- **Feature Expansion**: This design does not aim to add new features (like cloud transcription or advanced audio processing) but rather to stabilize the existing ones.
- **Complete Rewrite**: While refactoring is planned, we are not replacing the core libraries (e.g., `faster-whisper`, `rumps`) but rather how they are orchestrated.

## Decisions

**1. Architecture: Modular Core-Centric Design**
- **Decision**: We will move from a single file to a package-based structure. The core logic (the "Engine") will be independent of the UI and API layers.
- **Rationale**: This allows for easier testing (unit tests for the engine without needing a menu bar) and prevents UI-related bugs from crashing the core processes.

**2. State Management: Centralized Finite State Machine (FSM)**
- **Decision**: Implement a single, thread-safe `StateController` that manages all transitions (IDLE -> RECORDING -> TRANSCRIBING -> IDLE).
- **Rationale**: The current `DictationState` is a collection of flags. A formal FSM ensures that only one state can be active at a time, preventing illegal transitions (e.g., starting a recording while already transcribing).

**3. Concurrency: Worker-Thread Model**
- **Decision**: Use dedicated worker threads for long-running tasks (recording, transcription) and a main thread/event loop for the UI.
- **Rationale**: This prevents the UI from freezing during heavy transcription tasks and ensures that hardware events (Fn key) can be handled immediately.

**4. Interface: Event-Driven Communication**
- **Decision**: The Core Engine will communicate with the UI and API via an event/callback mechanism.
- **Rationale**: This decouples the "how" of the UI (rumps) from the "what" of the engine, allowing us to swap or test components independently.

## Risks / Trade-offs

- **[Risk] Increased Complexity**: Moving from one file to multiple modules increases the complexity of the project structure.
  - **Mitigation**: Use clear, consistent naming conventions and a well-defined directory structure.
- **[Risk] Threading Overhead**: Managing multiple threads and a central state machine introduces potential for deadlocks or race conditions if not handled carefully.
  - **Mitigation**: Use strict locking mechanisms and a single-entry point for state transitions (the FSM).
- **[Risk] Refactoring Regressions**: Changing the architecture might break existing functionality.
  - **Mitigation**: We will use a "test-driven" approach where we verify existing behavior before and after each module extraction.

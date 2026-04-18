## Why

The current project, while functional, was developed using a "vibecoding" approach where architectural decisions were made incrementally without a central blueprint. This has led to tight coupling between the UI, state management, and hardware-level interactions (macOS event taps), making it difficult to verify correctness, handle edge cases (like race conditions during transcription/recording transitions), and scale the feature set. This retrospective aims to formalize the system's logic into a robust specification to identify design flaws and provide a roadmap for stabilization.

## What Changes

- **Formalized System Specification**: Transition from implicit logic to an explicit, documented state machine and capability set.
- **Architectural Decoupling**: Separation of the core engine (recording/transcription) from the UI (rumps) and the interface layer (HTTP server).
- **State Machine Hardening**: Implementation of a more robust state management system to prevent race conditions between recording, transcription, and user input.
- **Permission & Security Audit**: Formalizing the requirements for macOS permissions (Input Monitoring, Accessibility) to ensure reliable operation.
- **Refactoring of the "Single File Core"**: Breaking down `whispy.py` into modular, testable components following the new specification.

## Capabilities

### New Capabilities
- `core-engine`: The central logic for managing recording, transcription, and audio file lifecycle.
- `event-listener`: The hardware interaction layer (Fn key detection via CGEventTap).
- `text-injection`: The mechanism for simulating keystrokes or clipboard actions.
- `api-interface`: The HTTP server layer for external control and status reporting.

### Modified Capabilities
- `state-management`: Refactoring the global `DictationState` into a structured, thread-safe state machine.
- `ui-controller`: Decoupling the menu bar UI from the core logic to allow for easier testing and updates.

## Impact

- **Codebase**: Significant refactoring of `whispy.py` into a modular structure.
- **Dependencies**: Potential introduction of more structured testing tools or state machine libraries if required by the design.
- **System**: Requires consistent macOS permissions (Accessibility, Input Monitoring) to function as intended.

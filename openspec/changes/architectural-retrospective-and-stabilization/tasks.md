## Task List

### Phase 1: Project Scaffolding & Environment Setup
- [ ] Create new directory structure for the modularized project.
- [ ] Set up a base Python package structure (e.g., `src/whispy/`).
- [ ] Initialize a test environment to verify the new structure.

### Phase 2: Core Engine Extraction (The "Brain")
- [ ] Extract `DictationState` and core logic into `src/whispy/core/engine.py`.
- [ ] Implement the formal State Machine (FSM) in `src/whispy/core/state_machine.py`.
- [ ] Implement the audio recording and transcription logic in `src/whispy/core/audio.py`.
- [ ] Verify the core engine works in isolation via a test script.

### Phase 3: Hardware & Interface Extraction (The "Senses")
- [ ] Extract the Fn key listener into `src/whispy/hardware/event_tap.py`.
- [ ] Extract text injection logic into `src/whispy/hardware/injection.py`.
- [ ] Integrate the listener and injection with the new core engine.

### Phase 4: UI & API Integration (The "Face")
- [ ] Extract the HTTP server into `src/whispy/api/server.py`.
- [ ] Extract the Menu Bar UI into `src/whispy/ui/menu_bar.py`.
- [ ] Re-integrate all modules into the main entry point (`whispy.py`).

### Phase 5: Verification & Stabilization
- [ ] Perform a full audit against the `specs/` to ensure all requirements are met.
- [ ] Run stress tests (rapid Fn key presses, simultaneous API calls) to ensure stability.
- [ ] Final cleanup and documentation of the new architecture.

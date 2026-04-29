## Context

The Whispy menu bar UI currently exposes three configuration menus:
1. **Model** — model size selection (kept)
2. **Language** — language selection with "auto" option (simplified)
3. **Compute** — compute backend selection (removed)
4. **Trigger Key** — trigger key selection with "learn" option (removed)

The Compute and Trigger Key menus add complexity for features that most users never need. The "auto" language option is unreliable for short audio clips.

## Goals / Non-Goals

**Goals:**
- Remove the Trigger Key menu entirely (always use "fn" keycode 44)
- Remove the Compute menu entirely (always use "cpu-int8")
- Remove "auto" from Language menu (keep "fr" and "en" only)
- Keep the Model menu (model size selection is useful)
- Keep the Copy to clipboard toggle (useful feature)

**Non-Goals:**
- Removing the Model menu (model selection is a core feature)
- Adding a settings/preferences panel
- Supporting custom trigger keys via UI

## Decisions

### Decision: Hardcode trigger key to "fn" (keycode 44)
- **Why:** The Fn key is the standard trigger for Whispy. Custom trigger keys add complexity for rare use cases.
- **Alternatives considered:**
  - Keep the menu but make it read-only → adds UI clutter for no benefit
  - Support custom trigger keys via keyboard shortcut → over-engineering

### Decision: Hardcode compute backend to "cpu-int8"
- **Why:** Apple Silicon Macs (the only supported platform) perform best with cpu-int8. CUDA is not available on macOS.
- **Alternatives considered:**
  - Keep the menu but only show "cpu-int8" → same as removing it
  - Auto-detect best compute backend → adds complexity, cpu-int8 is always optimal on Apple Silicon

### Decision: Remove "auto" from language selection
- **Why:** Auto-detection requires >= 1s of audio and is unreliable for short dictation clips.
- **Alternatives considered:**
  - Keep "auto" but add a warning → adds UI complexity
  - Make "auto" the first option but not default → doesn't solve the reliability issue

## Risks / Trade-offs

[Risk] Users who need a custom trigger key can no longer configure it
→ Mitigation The Fn key works for most users. Custom triggers are a rare edge case.

[Risk] Users on Intel Macs lose compute options
→ Mitigation cpu-int8 works on all platforms. The "or make it work" in the TODO suggests fixing is preferred over removing, but compute options are not viable on macOS.

[Risk] Users who prefer auto-detect language lose that option
→ Mitigation Users can still switch to "en" or "fr" as needed. Auto-detect is unreliable for short clips anyway.

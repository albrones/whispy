# Spec Delta

## Purpose

Gives Whispy users an OS-aware, interactive documentation site, generated from the code's own configuration schema and diagnostic checks, that helps them install, troubleshoot and configure the app without reading instructions meant for another platform.

## ADDED Requirements

### Requirement: Static documentation served from the website
The documentation SHALL be static HTML, CSS and JavaScript under `website/docs/`, served by the existing site host with no build step, package install or backend. Pages SHALL link to each other and to the landing page with relative URLs.

#### Scenario: Docs render from a static host
- **WHEN** `website/docs/index.html` is served by a plain static file server
- **THEN** every docs page and widget renders and works without any server-side code

#### Scenario: Docs work offline once loaded
- **WHEN** a docs page is opened with no network access from a local checkout
- **THEN** layout, navigation and widgets work because every required asset is local

### Requirement: Generated output is committed and kept fresh
The committed contents of `website/docs/` SHALL be byte-identical to what the documentation generator produces from the current sources. A test SHALL fail when they differ and SHALL name the command that regenerates them.

#### Scenario: Stale docs fail the suite
- **WHEN** a configuration key's description is changed without regenerating the docs
- **THEN** the freshness test fails and its message names the regeneration command

#### Scenario: Regenerated docs pass
- **WHEN** the generator is run and its output committed
- **THEN** the freshness test passes

#### Scenario: Generation is deterministic
- **WHEN** the generator runs twice on unchanged sources
- **THEN** both runs produce identical files

### Requirement: Global operating-system switcher
Every docs page SHALL offer a macOS / Linux switcher. Content specific to one OS SHALL be shown only when that OS is selected. The choice SHALL persist across pages and visits on the same browser, and SHALL default to the visitor's detected OS, falling back to macOS.

#### Scenario: Linux selection hides macOS steps
- **WHEN** the visitor selects Linux on the install page
- **THEN** macOS-only steps (Accessibility, Input Monitoring, `make app`) are hidden and Linux steps (X11 session, `xdotool`, `systemd --user`) are shown

#### Scenario: Choice persists across pages
- **WHEN** the visitor selects Linux and then opens the troubleshooting page
- **THEN** the troubleshooting page opens with Linux selected

#### Scenario: Storage unavailable
- **WHEN** browser storage is blocked
- **THEN** the switcher still works for the current page and falls back to the detected OS on the next page

### Requirement: Content works without JavaScript
With JavaScript disabled, every docs page SHALL still show all of its content, with OS-specific sections labelled by OS, and the config reference table SHALL be readable.

#### Scenario: No-JS reader sees both platforms
- **WHEN** a docs page is loaded with JavaScript disabled
- **THEN** both macOS and Linux sections are visible, each labelled with its OS

### Requirement: Install guide with copyable steps
The install page SHALL present the one-line installer and the per-OS manual steps, each command with a copy button, as a checklist the visitor can tick off. The page SHALL state the first-run model download size.

#### Scenario: Copy the one-liner
- **WHEN** the visitor clicks the copy button next to the one-line installer
- **THEN** the exact command shown is placed on the clipboard and the button confirms the copy

#### Scenario: Checklist progress
- **WHEN** the visitor ticks the first two install steps and reloads the page
- **THEN** those two steps are still ticked when storage is available

### Requirement: Troubleshooting tree mirrors the diagnostic checks
The troubleshooting page SHALL guide the visitor from a symptom to a fix through a decision tree. Every diagnostic check run by `make doctor` SHALL be reachable as a leaf showing the check's name, how to fix it on the selected OS, and an instruction to run `make doctor` to confirm.

#### Scenario: Symptom to fix
- **WHEN** a macOS visitor chooses "Pressing the trigger does nothing"
- **THEN** the tree leads to the Input Monitoring check with the System Settings path to grant it

#### Scenario: Every check is documented
- **WHEN** the docs are generated
- **THEN** generation fails if a `doctor` check has no troubleshooting entry, or an entry names a check that no longer exists

### Requirement: Config builder bounded by the schema
The config page SHALL offer an input for every configuration key, initialised to its default and limited to the values the daemon accepts, and SHALL output a `config.json` the visitor can copy. The output SHALL contain only keys whose value differs from the default.

#### Scenario: Out-of-range value cannot be produced
- **WHEN** the visitor tries to set `vad_aggressiveness` to 5
- **THEN** the input does not allow it, because the accepted range is 0 to 3

#### Scenario: Cross-key constraint is enforced
- **WHEN** the visitor sets `max_chunk_s` lower than or equal to `min_chunk_s`
- **THEN** the builder flags the value as invalid and does not emit it

#### Scenario: Only changes are emitted
- **WHEN** the visitor changes `trigger_mode` to `toggle` and nothing else
- **THEN** the generated JSON is exactly `{"trigger_mode": "toggle"}`

#### Scenario: Output is accepted by the daemon
- **WHEN** any JSON produced by the builder is loaded by the daemon's config loader
- **THEN** every value is kept, with no validation warning

### Requirement: Complete configuration reference
The config page SHALL include a reference table listing every configuration key with its default, its accepted values and its description, generated from the configuration schema, and SHALL contain no key the schema does not define.

#### Scenario: Reference matches the schema
- **WHEN** the generated reference table's keys are compared with the configuration schema's keys
- **THEN** the two sets are equal and every listed default equals the schema default

### Requirement: Streaming segmentation visualizer
The config page SHALL show an animated audio timeline that illustrates where a recording is cut into chunks for the current values of `pause_ms`, `min_speech_s`, `soft_gap_ms`, `min_chunk_s` and `max_chunk_s`, updating when the visitor changes them. The animation SHALL be disabled when the visitor prefers reduced motion, leaving a static illustration.

#### Scenario: Longer pause merges chunks
- **WHEN** the visitor raises `pause_ms` above the length of a pause in the sample timeline
- **THEN** the cut at that pause disappears and the two chunks merge

#### Scenario: Illustration is labelled as such
- **WHEN** the visualizer is shown
- **THEN** it states that it is a simplified illustration of the segmentation rules, not a recording of the real segmenter

#### Scenario: Reduced motion
- **WHEN** the visitor has `prefers-reduced-motion` enabled
- **THEN** the timeline is drawn without animation

### Requirement: Usage and FAQ page
The docs SHALL include a page covering trigger modes (hold and toggle), the local HTTP API with authenticated examples, where the logs are, how to restart, and how to uninstall, for each OS.

#### Scenario: API examples are authenticated
- **WHEN** the usage page shows a `curl` example against the local API
- **THEN** the example includes the bearer-token header and says where the token file is

### Requirement: Docs follow the site's accessibility baseline
Docs pages SHALL use the site's brand accent and dark theme, adapt to narrow viewports without horizontal scroll, keep every widget operable by keyboard, and respect `prefers-reduced-motion`.

#### Scenario: Keyboard-only navigation
- **WHEN** a visitor uses only the keyboard
- **THEN** the OS switcher, troubleshooting tree, checklist and config builder can all be reached and operated

#### Scenario: Narrow viewport
- **WHEN** a docs page is viewed at 360px width
- **THEN** there is no horizontal page scroll

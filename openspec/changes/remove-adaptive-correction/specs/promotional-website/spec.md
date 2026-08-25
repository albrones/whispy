## ADDED Requirements

### Requirement: Site claims match shipped behavior
The promotional site SHALL only promote features that are active in the shipped
application. It SHALL NOT claim adaptive correction learning ("learns your words",
"remembers your corrections", or equivalent copy) while that feature is absent. The
animated menu-bar demo's dropdown SHALL depict the real menu: it SHALL include a
"Trigger" submenu entry and SHALL NOT include a "Learned Words" entry.

#### Scenario: No adaptive-learning claim on the page
- **WHEN** `tests/test_website.py` scans `website/index.html`
- **THEN** no feature card or copy claims that Whispy learns from user corrections

#### Scenario: Menu demo shows the Trigger submenu
- **WHEN** a visitor watches the animated menu-bar demo
- **THEN** the dropdown includes a "Trigger" entry alongside Model and Language, and
  no "Learned Words" entry

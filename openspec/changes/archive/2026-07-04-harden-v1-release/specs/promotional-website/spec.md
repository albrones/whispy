## ADDED Requirements

### Requirement: Site copy and demo match the app's default language
The promotional site's copy and animated menu-bar demo SHALL present English as the default dictation language, consistent with the app's `DEFAULT_CONFIG`, while noting that other languages (e.g. French) remain available from the menu.

#### Scenario: Feature copy states the default language
- **WHEN** a visitor reads the "Multilingual" feature card
- **THEN** it SHALL state that Whispy defaults to English, with other languages (e.g. French) available from the menu bar

#### Scenario: Animated demo opens in English
- **WHEN** the animated menu-bar demo plays its dictation loop
- **THEN** it SHALL start in English and demonstrate switching to another language from the tray, matching the app's actual default rather than starting in French

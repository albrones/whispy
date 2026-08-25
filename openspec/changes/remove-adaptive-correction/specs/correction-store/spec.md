## REMOVED Requirements

### Requirement: Persistent correction storage
**Reason**: Adaptive correction is deleted; nothing writes corrections anymore. Existing `~/.config/whispy/corrections.json` files are left in place (harmless, 0600) — deleting user files is riskier than orphaning them.
**Migration**: None for users. The store design is preserved via git history (`b18c8c6`) and the tracking issue.

### Requirement: Correction removal via menu bar
**Reason**: The "Learned Words" menu is removed together with the store it managed.
**Migration**: None; the menu always displayed "No learned words yet" while the feature was gated off.

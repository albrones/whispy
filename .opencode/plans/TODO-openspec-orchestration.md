# Orchestration des 7 tâches TODO avec OpenSpec

## Contexte
- Projet: whispy (macOS speech-to-text daemon)
- Tests: 184 tests, tous passing (base known good)
- Workflow par tâche: OpenSpec Propose → Apply → Archive → Commit → TODO mark done

## Tâche 1: Default config params
**Objectif**: Changer les defaults: language "fr", copy_to_clipboard false (les autres defaults sont déjà corrects)

### Sous-agents nécessaires:
1. **Agent implémentation**: Modifier `DEFAULT_CONFIG` dans `engine.py` + update spec
2. **Agent tests**: Ajouter test de validation des defaults + run full test suite

## Tâche 2: Update default params / save locally
## Tâche 3: Remove trigger key selection
## Tâche 4: Remove compute selection
## Tâche 5: Remove language selection 'auto'
## Tâche 6: Improve recording visual
## Tâche 7: Static website + CICD

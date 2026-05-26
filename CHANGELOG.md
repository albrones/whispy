# Changelog V1 — Whispy

**Date de release:** 2026-05-26

## [Unreleased]

### Ajoutés
- Module `src/whispy/core/config.py` : validation et migration de config
- Module `src/whispy/core/text_cleaner.py` : stripping des credits Whisper
- Tests d'erreur (`test_error_handling.py`) : sox manquant, micro indisponible, engine sans modèle
- Migration automatique de config (versioning via `_version`)
- Validation des valeurs de config (`model_size`, `language`, `beam_size`, etc.)

### Modifiés
- Extraction `load_config` / `save_config` de `engine.py` vers `config.py`
- Unification du model loading (`_load_model_async` + `_load_model_on_device` → `_load_model_async`)
- Clarification de la visualisation active (indicator par défaut)
- Logging amélioré des transitions FSM
- Correction des tests qui hang (mock `afplay` subprocess)

### Supprimés
- `whispy_legacy.py` (redondant avec `whispy_daemon.py`)

### Documentation
- `AGENTS.md` mis à jour avec la structure réelle du projet
- `SPECIFICATION.md` : sections obsolètes marquées
- README.md : instructions d'installation à jour

## Critères de sortie V1

- [x] Tous les tests passent (282 passed, 0 failure, 0 hang)
- [x] `install.sh` vérifie sox, permissions, LaunchAgent
- [x] Daemon démarre et s'arrête proprement
- [x] Recording → transcription → injection fonctionne
- [x] Config par défaut fonctionne sans fichier de config
- [x] README.md à jour avec instructions d'installation
- [x] Permissions macOS documentées
- [x] CHANGELOG.md pour la V1
- [ ] CI minimal configuré (en cours)

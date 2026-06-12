# Changelog V1 — Whispy

**Date de release:** 2026-05-26

## [Unreleased]

### Corrigés (préparation open source)
- **Bug : gel au démarrage de l'enregistrement.** `_wait_for_recording_ready`
  ne débloquait jamais le thread principal quand sox échouait ou dépassait le
  timeout (`ready.set()` manquant) — le daemon pouvait freezer. `ready.set()`
  est désormais garanti via `finally`.
- **Bug : crash de la visualisation ferrofluid.** `NSDefaultRunLoopMode`
  utilisé sans import dans `ferrofluid_view.py` → `NameError` au démarrage de
  l'animation. Import ajouté.
- Ré-câblage de la visualisation ferrofluid dans le cycle de vie du menu bar
  (débranchée par erreur), avec le correctif du crash ci-dessus.
- Réparation de 21 tests cassés/bloquants (signature de callback event tap,
  comportement FSM de récupération, câblage ferrofluid, fixture API qui
  hangait sur la transcription).
- Doublons de keycodes nettoyés dans `event_tap.py` (`51` mappait `m` ET
  `backspace`, `f13`-`f20` dupliqués).

### Outillage & qualité
- Commande de diagnostic `python whispy_daemon.py --doctor` (`make doctor`) :
  vérifie sox, le modèle, les 3 permissions macOS et l'état du daemon.
- Migration du lint vers **Ruff** (lint + format) ; suppression de flake8.
- `Makefile`, `.pre-commit-config.yaml`, dépendance dev `ruff`.
- CI : matrice Python 3.10/3.11/3.12, `ruff check` + `ruff format --check`.

### Open source
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, templates d'issue et de PR.
- URLs réelles du dépôt (`albrones/whispy`) ; placeholders supprimés.
- `graphify-out/` retiré du versioning (artefact généré, ~7,6 Mo) et ignoré.
- Documentation déplacée sous `docs/` ; stockage des modèles documenté.

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

- [x] Tous les tests passent (297 passed, 0 failure, 0 hang)
- [x] `install.sh` vérifie sox, permissions, LaunchAgent
- [x] Daemon démarre et s'arrête proprement
- [x] Recording → transcription → injection fonctionne
- [x] Config par défaut fonctionne sans fichier de config
- [x] README.md à jour avec instructions d'installation
- [x] Permissions macOS documentées
- [x] CHANGELOG.md pour la V1
- [x] CI configurée (GitHub Actions : lint Ruff + tests sur Python 3.10–3.12)

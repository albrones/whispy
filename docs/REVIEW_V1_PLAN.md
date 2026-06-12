# Whispy — Audit Global & Plan de Stabilisation pour la V1

**Date:** 2026-05-25
**Statut:** Audit initial
**Objectif:** Livrer la V1 de Whispy avec confiance

---

## 1. Vue d'ensemble du projet

Whispy est une application macOS menu-bar de speech-to-text en temps réel.
Elle écoute la touche Fn, enregistre l'audio via `sox`, le transcrit avec `faster-whisper`
et injecte le texte dans l'application active.

**Architecture actuelle:**
```
src/whispy/
├── core/
│   ├── __init__.py       → Engine, DictationState, load/save_config
│   ├── engine.py          → Moteur principal (20K lignes)
│   ├── state_machine.py   → FSM pour recording/transcription
│   └── audio.py           → AudioEngine (sox recording, playback)
├── hardware/
│   ├── __init__.py
│   ├── event_tap.py       → CGEventTap pour détection Fn key
│   └── injection.py       → Text injection (osascript + clipboard)
├── ui/
│   ├── menu_bar.py        → rumps menu bar app
│   ├── indicator_window.py → Floating dot indicator
│   ├── ferrofluid_window.py → Ferrofluid visualization window
│   ├── ferrofluid_view.py → CoreGraphics ferrofluid renderer
│   └── audio_level.py     → sounddevice audio level monitor
└── api/
    └── server.py          → HTTP API (localhost:9090)
whispy_daemon.py           → Point d'entrée (entry point)
```

**Dépendances:** `faster-whisper`, `pyobjc-framework-Quartz`, `rumps`, `sounddevice`, `sox` (system)

---

## 2. Audit des problèmes identifiés

### 2.1. CRITIQUE — Fichiers morts / obsolètes

| Fichier | Problème |
|---------|----------|
| `whispy_legacy.py` | Ancien entry point, identique à `whispy_daemon.py` à 95%. Peut être supprimé. |
| `whispy.py` | Supprimé (shadowing du package), mais la doc mentionne encore `whispy.py` comme entry point. |
| `src/whispy/core/text_cleaner.py` | **N'existe pas!** Le spec `text-cleaning/spec.md` décrit un text cleaner mais le fichier n'a jamais été créé. |
| `src/whispy/core/config.py` | **N'existe pas!** Le config loading est inline dans `engine.py` au lieu d'être dans un module dédié. |

### 2.2. CRITIQUE — Point d'entrée documenté inexistant

La doc (`AGENTS.md`, `SPECIFICATION.md`) mentionne `whispy.py` comme entry point.
Le fichier réel est `whispy_daemon.py`. Cette divergence crée de la confusion.

### 2.3. IMPORTANT — Tests qui plantent / hang

| Test | Problème |
|------|----------|
| `test_post_start` | **HANG** — Le test bloque indéfiniment. `POST /start` appelle `engine.start_recording()` qui appelle `AudioEngine.start()` qui lance `sox` via subprocess. Le mock de `subprocess.Popen` dans le fixture ne couvre pas tous les chemins. |
| `test_post_stop` | Potentiellement le même problème. |
| `test_e2e.py` | 42 tests — le fichier existe mais le plan E2E mentionne 85 tests qui "passaient" lors de l'archive. Il faut vérifier si les fixes ont été appliqués. |
| `test_event_tap_e2e.py` | 43 tests — même vérification nécessaire. |
| `test_simplify_config_ui.py` | 12 tests — à vérifier. |
| `test_config_validation.py` | À vérifier. |

**Note:** Le test run complet a timeouté à 60s, ce qui confirme que des tests hang.

### 2.4. IMPORTANT — Split du model loading

Dans `engine.py`, il y a **deux** méthodes de chargement de modèle:
- `_load_model_async()` — chargement asynchrone classique
- `_load_model_on_device()` — chargement device-specific avec fallback

Ces deux méthodes coexistent. Il faut unifier.

### 2.5. IMPORTANT — Code duplication engine.py

`engine.py` fait ~500 lignes et gère:
- Chargement du modèle Whisper
- Gestion de la FSM
- Audio recording (sox)
- Transcription worker
- Text injection
- Config loading/saving
- Status callbacks

C'est un **god class** qui devrait être découpé.

### 2.6. MOYEN — UI: ferrofluid vs indicator

L'application a **deux** visualisations de state:
1. `indicator_window.py` — petit point emoji (simple, léger)
2. `ferrofluid_window.py` + `ferrofluid_view.py` — visualisation sophistiquée (lourde, CoreGraphics)

Il n'est pas clair laquelle est active par défaut. L'UI menu bar (`menu_bar.py`) gère les deux.

### 2.7. MOYEN — Config: pas de validation

`load_config()` fait un fallback sur les defaults si le JSON est corrompu, mais:
- Pas de validation des valeurs (ex: `model_size` doit être dans une liste)
- Pas de migration de config (si de nouvelles clés sont ajoutées)
- `copy_to_clipboard` est un booléen mais le spec parle de modes (clipboard vs keystroke)

### 2.8. MOYEN — Text cleaner inexistant

Le spec `text-cleaning/spec.md` définit des scenarios pour stripping de credits Whisper,
mais le fichier `text_cleaner.py` n'a jamais été créé. Le code dans `engine.py` fait le stripping
en dur dans `_transcription_worker()`.

### 2.9. MOYEN — Documentation divergente

| Doc | État |
|-----|-----|
| `AGENTS.md` | Mentionne `whispy.py` (inexistant) |
| `SPECIFICATION.md` | 20K lignes, très détaillé mais partiellement obsolète |
| `CONTEXT.md` | 3.9K lignes, bon mais pas à jour |
| `openspec/specs/` | Specs existants mais certains ont `TBD` dans le purpose |
| `graphify-out/` | Graph existant mais à vérifier |

### 2.10. mineur — Dependencies: `rumps` est abandonné

`rumps` (menu bar UI) n'est plus maintenu activement. Pour la V1, c'est acceptable
mais à noter comme risque à long terme.

### 2.11. mineur — Pas de CI/CD

Aucun fichier de CI (GitHub Actions, etc.). La vérification est purement manuelle.

### 2.12. mineur — `sox` en dépendance system

`sox` n'est pas listé dans les dependencies Python. L'install.sh doit le vérifier/installer.

---

## 3. Plan d'action pour la V1

### Phase 1: Nettoyage immédiat (1-2h)

**Objectif:** Éliminer les fichiers morts et les incohérences documentaires.

- [ ] 1.1 Supprimer `whispy_legacy.py` (identique à `whispy_daemon.py`)
- [ ] 1.2 Unifier le nom de l'entry point: choisir `whispy_daemon.py` ET mettre à jour TOUTES les refs (install.sh, AGENTS.md, SPECIFICATION.md, plist)
- [ ] 1.3 Créer `src/whispy/core/text_cleaner.py` avec les fonctions de stripping de credits (implémenter le spec text-cleaning)
- [ ] 1.4 Extraire `load_config` et `save_config` de `engine.py` vers `src/whispy/core/config.py`
- [ ] 1.5 Mettre à jour `AGENTS.md` pour refléter la structure réelle

### Phase 2: Stabilisation des tests (2-4h)

**Objectif:** Tous les tests passent sans hang.

- [ ] 2.1 Identifier les tests qui hang: `pytest --timeout=10` par fichier
- [ ] 2.2 Fix `test_post_start` et `test_post_stop` — mock `afplay` subprocess call
- [ ] 2.3 Fix `test_post_stop` — mock `afplay` subprocess call
- [ ] 2.4 Fix `test_post_stop` — mock `afplay` subprocess call
- [ ] 2.5 Fix `test_post_stop` — mock `afplay` subprocess call
- [ ] 2.6 Fix `test_post_stop` — mock `afplay` subprocess call

### Phase 3: Refactoring du code (4-8h)

**Objectif:** Code plus maintenable, moins de god-class.

- [ ] 3.1 Déplacer le text cleaning de `_transcription_worker()` vers `text_cleaner.py`
- [ ] 3.2 Unifier `_load_model_async()` et `_load_model_on_device()` en une seule méthode
- [ ] 3.3 Ajouter validation de config dans `load_config()` (valider model_size, language, etc.)
- [ ] 3.4 Ajouter migration de config (si nouvelles clés ajoutées, migrer automatiquement)
- [ ] 3.5 Clarifier quelle visualisation est active (indicator vs ferrofluid) — choisir une par défaut
- [ ] 3.6 Ajouter logging pour le debug de la FSM (transitions non documentées)

### Phase 4: Tests additionnels (2-4h)

**Objectif:** Couvrir les gaps identifiés.

- [ ] 4.1 Tests unitaires pour `text_cleaner.py` (cover tous les scenarios du spec)
- [ ] 4.2 Tests de validation de config (valeurs invalides, migration)
- [ ] 4.3 Tests d'injection de texte (clipboard + keystroke modes)
- [ ] 4.4 Tests de la FSM (toutes transitions, états invalides)
- [ ] 4.5 Test d'erreur: que se passe-t-il si sox n'est pas installé?
- [ ] 4.6 Test d'erreur: que se passe-t-il si le micro est indisponible?

### Phase 5: Documentation et livraison (2-3h)

**Objectif:** Documentation à jour, ready pour la V1.

- [ ] 5.1 Mettre à jour `SPECIFICATION.md` (marquer les sections obsolètes)
- [ ] 5.2 Créer un `CHANGELOG.md` pour la V1
- [ ] 5.3 Mettre à jour le `README.md` avec les instructions d'installation à jour
- [ ] 5.4 Vérifier le `install.sh` (sox check, permissions, LaunchAgent)
- [ ] 5.5 Créer un `.github/workflows/ci.yml` minimal (pytest + lint)
- [ ] 5.6 Taguer la V1 et créer un release note

---

## 4. Risques identifiés

| Risque | Impact | Mitigation |
|--------|--------|------------|
| `rumps` abandonné | UI menu bar peut casser sur future macOS | Acceptable pour V1; migrer vers `AppKit` natif si nécessaire |
| `sox` non installé | Recording ne fonctionne pas | Vérifier dans `install.sh`, message d'erreur clair |
| Permissions macOS | Micro + Accessibility + Input Monitoring | Documentation claire dans README |
| `faster-whisper` modèle lourd | First launch slow | Charger en async, montrer un spinner |
| Pas de CI | Regression non détectée | Ajouter CI minimal (Phase 5) |

---

## 5. Priorisation recommandée

1. **Immédiat (Phase 1):** Nettoyage fichiers morts + unification entry point
2. **Urgent (Phase 2):** Fix des tests qui hang — sans tests fiables, on ne peut pas livrer
3. **Important (Phase 3):** Refactoring code — text cleaner, config validation, unification model loading
4. **Avant livraison (Phase 4):** Tests additionnels pour les gaps
5. **Avant release (Phase 5):** Documentation + CI

---

## 6. Critères de sortie V1

- [ ] Tous les tests passent (0 failure, 0 hang)
- [ ] `install.sh` fonctionne sur un macOS propre
- [ ] Daemon démarre et s'arrête proprement
- [ ] Recording → transcription → injection fonctionne (manuellement vérifié)
- [ ] Config par défaut fonctionne sans fichier de config
- [ ] README.md à jour avec instructions d'installation
- [ ] Permissions macOS documentées
- [ ] CHANGELOG.md pour la V1
- [ ] CI minimal configuré

# Wispy

Dictée vocale locale pour macOS via [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Maintenez la touche **Fn** pour enregistrer, relâchez pour transcrire le texte automatiquement dans le champ actif.

Tout tourne en local, aucune donnée n'est envoyée sur internet.

## Installation rapide

```bash
git clone https://github.com/<ton-user>/wispy.git
cd wispy
./install.sh
```

## Prérequis

- **macOS** (Apple Silicon ou Intel)
- [Homebrew](https://brew.sh)
- `sox` (`brew install sox`)

## Installation détaillée

### 1. Installer les dépendances

```bash
brew install sox
```

### 3. Cloner et lancer l'install

```bash
git clone https://github.com/<ton-user>/wispy.git
cd wispy
./install.sh
```

Le script gère automatiquement :
- Création du virtual environment Python
- Installation de faster-whisper
- Installation et lancement du LaunchAgent

Pour utiliser un modèle différent :
```bash
WHISPER_MODEL=medium ./install.sh  # small, base, tiny, medium, large-v3
```

### 5. Configurer les permissions macOS

C'est l'étape la plus importante. Sans ces permissions, le daemon ne peut ni enregistrer ni taper du texte.

#### 5a. Microphone

Le daemon a besoin du micro pour capturer l'audio.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Microphone**
2. Activer **iTerm** (ou Terminal)
3. Le daemon (`python`) peut aussi demander l'accès au micro lors du premier enregistrement — accepter la popup

#### 5b. Accessibilité

Le daemon a besoin de cette permission pour simuler la frappe clavier via `osascript`.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Accessibilité**
2. Cliquer sur **"+"** et ajouter le python du venv (`wispy/.venv/bin/python3`)
3. Vérifier que le toggle est **activé**

> **Sans cette permission**, la transcription fonctionne mais le texte ne s'écrit pas dans le champ actif (erreur `osascript timeout` dans les logs).



### 6. Redémarrer le daemon après les permissions

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.wispy.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.wispy.plist
```

## Utilisation

1. Placer le curseur dans un champ de texte (iTerm, navigateur, éditeur...)
2. **Maintenir Fn** → son "Tink" = enregistrement en cours
3. **Parler**
4. **Relâcher Fn** → son "Pop" = transcription et frappe automatique

## Modèles Whisper

| Modèle | Taille | Vitesse | Qualité FR |
|--------|--------|---------|------------|
| tiny   | 75 Mo  | ++++    | --         |
| base   | 142 Mo | +++     | -          |
| small  | 466 Mo | ++      | ++         |
| medium | 1.5 Go | +       | +++        |
| large-v3 | 2.9 Go | -     | ++++       |

Le modèle par défaut est `small` (plus rapide). Pour changer :

```bash
WHISPER_MODEL=medium ./install.sh
```

## Commandes manuelles

```bash
curl http://localhost:9090/status                          # Statut du daemon
curl -X POST http://localhost:9090/start                   # Démarrer l'enregistrement
curl -X POST http://localhost:9090/stop                    # Arrêter et transcrire
tail -f ~/.wispy.log ~/.wispy-error.log  # Logs en direct
```

### Mettre à jour faster-whisper

```bash
./.venv/bin/pip install --upgrade faster-whisper
```

## Dépannage

| Symptôme | Cause probable | Solution |
|-----------|---------------|----------|

| Son Tink/Pop mais pas de texte | Permission Accessibilité manquante | Étape 5b |
| Erreur `sox not found` dans les logs | sox pas dans le PATH du LaunchAgent | Relancer install.sh |
| Erreur `Operation not permitted` | Mauvais python (Xcode au lieu de Homebrew) | Relancer install.sh |
| Texte imprécis / erreurs | Modèle trop petit | `WHISPER_MODEL=medium ./install.sh` |
| Daemon ne démarre pas | Port 9090 occupé ou python introuvable | Vérifier les logs |
| Model non trouvé | Virtual env non créé | Relancer install.sh |

## Configuration

Modifier le haut de `wispy.py` pour changer :
- `PORT` — port HTTP (défaut : 9090)
- `WHISPER_MODEL_SIZE` — modèle (défaut : `small`)
- La langue est en français (`language="fr"`).

## Désinstallation

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.wispy.plist
rm ~/Library/LaunchAgents/com.wispy.plist
rm -rf wispy/.venv
```

---

## Licence

Ce projet est distribué sous licence **GPLv3**. Voir le fichier LICENSE pour plus de détails.
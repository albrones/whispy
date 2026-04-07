# Whisper Dictation

Dictée vocale locale pour macOS via [Whisper.cpp](https://github.com/ggerganov/whisper.cpp). Maintenez la touche **Fn** pour enregistrer, relâchez pour transcrire le texte automatiquement dans le champ actif.

Tout tourne en local, aucune donnée n'est envoyée sur internet.

## Installation rapide

```bash
# Cloner le repo avec le submodule whisper.cpp
git clone --recurse-submodules https://github.com/<ton-user>/whisper-dictation.git
cd whisper-dictation

# Lancer l'installation (build, modèle, daemon, Karabiner)
./install.sh
```

## Prérequis

- **macOS** (Apple Silicon ou Intel)
- [Homebrew](https://brew.sh)
- [Karabiner-Elements](https://karabiner-elements.pqrs.org/)
- `sox` (`brew install sox`)
- `cmake` (via Xcode CLI : `xcode-select --install`)
- Python 3 (`brew install python3`)

## Installation détaillée

### 1. Installer les dépendances

```bash
brew install sox python3
xcode-select --install
```

### 2. Installer Karabiner-Elements

Télécharger depuis https://karabiner-elements.pqrs.org/ puis ajouter `karabiner_cli` au PATH :

```bash
sudo ln -sf "/Library/Application Support/org.pqrs/Karabiner-Elements/bin/karabiner_cli" /usr/local/bin/karabiner_cli
```

Vérifier :
```bash
command -v karabiner_cli && echo "OK"
```

### 3. Cloner et lancer l'install

```bash
git clone --recurse-submodules https://github.com/<ton-user>/whisper-dictation.git
cd whisper-dictation
./install.sh
```

Le script gère automatiquement :
- Build de whisper.cpp (si pas déjà fait)
- Téléchargement du modèle (défaut : `medium`)
- Installation de la config Karabiner
- Installation et lancement du LaunchAgent

Pour utiliser un modèle différent :
```bash
WHISPER_MODEL=large-v3 ./install.sh
```

### 4. Activer la règle Karabiner

1. Ouvrir **Karabiner-Elements Settings**
2. Aller dans **Complex Modifications** → **Add rule**
3. Activer **"Hold Fn to record, release to transcribe"**

### 5. Configurer les permissions macOS

C'est l'étape la plus importante. Sans ces permissions, le daemon ne peut ni enregistrer ni taper du texte.

#### 5a. Microphone

Le daemon a besoin du micro pour capturer l'audio.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Microphone**
2. Activer **iTerm** (ou Terminal)
3. Le daemon (`python3`) peut aussi demander l'accès au micro lors du premier enregistrement — accepter la popup

> **Astuce** : si le bouton "+" est absent, glissez iTerm depuis le Finder (`/Applications/`) directement dans la liste.

#### 5b. Accessibilité

Le daemon a besoin de cette permission pour simuler la frappe clavier via `osascript`.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Accessibilité**
2. Cliquer sur **"+"** et ajouter `/opt/homebrew/bin/python3`
3. Vérifier que le toggle est **activé**

> **Sans cette permission**, la transcription fonctionne mais le texte ne s'écrit pas dans le champ actif (erreur `osascript timeout` dans les logs).

#### 5c. Suivi des entrées (Input Monitoring)

Nécessaire pour que Karabiner-Elements capture les touches.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Suivi des entrées**
2. Activer **Karabiner-Elements** et **karabiner_observer**

### 6. Redémarrer le daemon après les permissions

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.whisper-dictation.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whisper-dictation.plist
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

Le modèle par défaut est `medium`. Pour changer :

```bash
WHISPER_MODEL=large-v3 ./install.sh
```

Et modifier la ligne `ggml-medium.bin` dans `whisper-dictation.py` pour matcher.

## Commandes manuelles

```bash
curl http://localhost:9090/status                          # Statut du daemon
curl -X POST http://localhost:9090/start                   # Démarrer l'enregistrement
curl -X POST http://localhost:9090/stop                    # Arrêter et transcrire
tail -f ~/.whisper-dictation.log ~/.whisper-dictation-error.log  # Logs en direct
```

## Dépannage

| Symptôme | Cause probable | Solution |
|-----------|---------------|----------|
| Pas de son Tink au maintien de Fn | Règle Karabiner non activée | Étape 4 |
| Son Tink/Pop mais pas de texte | Permission Accessibilité manquante | Étape 5b |
| Erreur `sox not found` dans les logs | sox pas dans le PATH du LaunchAgent | Relancer install.sh |
| Erreur `Operation not permitted` | Mauvais python3 (Xcode au lieu de Homebrew) | Relancer install.sh |
| Texte imprécis / erreurs | Modèle trop petit | `WHISPER_MODEL=large-v3 ./install.sh` |
| Daemon ne démarre pas | Port 9090 occupé ou python3 introuvable | Vérifier les logs |

## Configuration

Modifier le haut de `whisper-dictation.py` pour changer :
- `PORT` — port HTTP (défaut : 9090)
- `WHISPER_MODEL` — chemin du modèle (défaut : `ggml-medium.bin`)
- La langue est en français (`-l fr`). Changer dans la fonction `transcribe()`.

## Désinstallation

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.whisper-dictation.plist
rm ~/Library/LaunchAgents/com.whisper-dictation.plist
rm ~/.config/karabiner/assets/complex_modifications/whisper-dictation.json
```

## Licence

MIT

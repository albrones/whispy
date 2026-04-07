# Whisper Dictation

Dictée vocale locale via Whisper.cpp. Maintenez la touche **Fn** pour enregistrer, relâchez pour transcrire le texte automatiquement dans le champ actif.

## Prérequis

- macOS (Apple Silicon ou Intel)
- [Homebrew](https://brew.sh)
- [Karabiner-Elements](https://karabiner-elements.pqrs.org/)
- sox (`brew install sox`)
- Python 3 (Homebrew : `/opt/homebrew/bin/python3`)
- whisper.cpp compilé dans `../whisper.cpp/`

## Installation

### 1. Installer les dépendances Homebrew

```bash
brew install sox
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

### 3. Cloner et compiler whisper.cpp

```bash
cd ~/Documents/Perso/tools   # ou votre dossier tools
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build --config Release -j$(sysctl -n hw.ncpu)
```

### 4. Télécharger le modèle Whisper

Le modèle `small` est utilisé par défaut (bon compromis qualité/vitesse pour le français) :

```bash
cd whisper.cpp/models
bash download-ggml-model.sh small
```

Modèles disponibles (du plus rapide au plus précis) :

| Modèle | Taille | Vitesse | Qualité FR |
|--------|--------|---------|------------|
| tiny   | 75 Mo  | ++++    | --         |
| base   | 142 Mo | +++     | -          |
| small  | 466 Mo | ++      | ++         |
| medium | 1.5 Go | +       | +++        |
| large  | 2.9 Go | -       | ++++       |

Pour changer de modèle, modifier `ggml-small.bin` dans `whisper-dictation.py` ligne 22 et relancer le daemon.

### 5. Lancer le script d'installation

```bash
cd ~/Documents/Perso/tools
./whisper-dictation/install.sh
```

### 6. Activer la règle Karabiner

1. Ouvrir **Karabiner-Elements Settings**
2. Aller dans **Complex Modifications** → **Add rule**
3. Activer **"Hold Fn to record, release to transcribe"**

### 7. Configurer les permissions macOS

C'est l'étape la plus importante. Sans ces permissions, le daemon ne peut ni enregistrer ni taper du texte.

#### 7a. Microphone

Le daemon a besoin du micro pour capturer l'audio.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Microphone**
2. Activer **iTerm** (ou Terminal)
3. Le daemon (`python3`) peut aussi demander l'accès au micro lors du premier enregistrement — accepter la popup

> **Astuce** : si le bouton "+" est absent, glissez iTerm depuis le Finder (`/Applications/`) directement dans la liste.

#### 7b. Accessibilité

Le daemon a besoin de cette permission pour simuler la frappe clavier via `osascript`.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Accessibilité**
2. Cliquer sur **"+"** et ajouter :
   - `/opt/homebrew/bin/python3`
   - Ou naviguer dans `/opt/homebrew/Cellar/python@3.13/` pour trouver le binaire python3
3. Vérifier que le toggle est **activé**

> **Sans cette permission**, la transcription fonctionne mais le texte ne s'écrit pas dans le champ actif (erreur `osascript timeout` dans les logs).

#### 7c. Suivi des entrées (Input Monitoring)

Nécessaire pour que Karabiner-Elements capture les touches.

1. Ouvrir **Réglages Système** → **Confidentialité et sécurité** → **Suivi des entrées**
2. Activer **Karabiner-Elements** et **karabiner_observer**

### 8. Redémarrer le daemon après les permissions

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.whisper-dictation.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whisper-dictation.plist
```

## Utilisation

1. Placer le curseur dans un champ de texte (iTerm, navigateur, éditeur...)
2. **Maintenir Fn** → son "Tink" = enregistrement en cours
3. **Parler**
4. **Relâcher Fn** → son "Pop" = transcription et frappe automatique

## Commandes manuelles

```bash
# Vérifier que le daemon tourne
curl http://localhost:9090/status
# {"recording": false}

# Enregistrer / arrêter manuellement
curl -X POST http://localhost:9090/start
curl -X POST http://localhost:9090/stop

# Lancer le daemon manuellement (debug)
python3 whisper-dictation.py

# Voir les logs en temps réel
tail -f ~/.whisper-dictation.log ~/.whisper-dictation-error.log
```

## Dépannage

| Symptôme | Cause probable | Solution |
|-----------|---------------|----------|
| Pas de son Tink au maintien de Fn | Règle Karabiner non activée | Étape 6 |
| Son Tink/Pop mais pas de texte | Permission Accessibilité manquante | Étape 7b |
| Erreur `sox not found` dans les logs | sox pas dans le PATH du LaunchAgent | Relancer install.sh |
| Erreur `Operation not permitted` | Mauvais python3 (Xcode au lieu de Homebrew) | Relancer install.sh |
| Texte imprécis / erreurs | Modèle trop petit | Passer à `medium` ou `large` (étape 4) |
| Daemon ne démarre pas | Port 9090 occupé ou python3 introuvable | Vérifier les logs |

## Désinstallation

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.whisper-dictation.plist
rm ~/Library/LaunchAgents/com.whisper-dictation.plist
rm ~/.config/karabiner/assets/complex_modifications/whisper-dictation.json
```

## Configuration

Modifier le haut de `whisper-dictation.py` pour changer :
- `PORT` — port HTTP (défaut : 9090)
- `WHISPER_MODEL` — chemin du modèle (défaut : `ggml-small.bin`)
- La langue est en français (`-l fr`). Changer dans la fonction `transcribe()`.

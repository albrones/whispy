## Why

Sous Omarchy (Arch + Hyprland, Wayland), la dictée F9 passe aujourd'hui par
Voxtype et Whisper small : moins précise et plus lente que Parakeet, le moteur
de Whispy V1. Whispy V1 refuse Wayland (« X11 requis ») : pas de hotkey
globale, pas d'injection.

**Besoin, en une phrase :** dans Omarchy, dicter avec F9 partout grâce à
Whispy V1 (Parakeet), plus précis et plus rapide que le Whisper small de
Voxtype ; V2 plus tard.

Décisions de cadrage (validées par l'utilisateur) :
- Whispy remplace Voxtype pour F9 ; Voxtype reste installé en secours.
- V1 d'abord.
- Déclencheur = la liaison Hyprland existante (F9 maintenue → `/start`,
  relâchée → `/stop`) via le dispatcher `omarchy-dictation` ; texte tapé avec
  `wtype`. Pas d'écoute evdev / groupe `input`.

## What Changes

- **Session Wayland sous Linux** : détectée au démarrage ; pas d'écouteur
  pynput (c'est le compositeur qui pilote `/start` et `/stop`) ; injection par
  `wtype` (le mode presse-papiers dépose aussi le texte avec `wl-copy`, comme
  `omarchy-clipboard-paste-text`) ; pas de tray pystray (Waybar ne montre pas
  l'icône XEmbed) — les erreurs passent par `notify-send`. X11 inchangé.
- **`POST /transcribe`** : corps `audio/wav` brut (16 kHz mono PCM 16 bits),
  même garde d'authentification, plafond de taille, réponse `{"text": …}`,
  erreurs JSON `{"error": …}` ; pas d'injection, aucun fichier gardé. C'est le
  contrat du client Régie.
- **Backend Omarchy** `packaging/omarchy/omarchy-dictation-whispy`
  (`start|stop|toggle`) lié dans `~/.local/bin` par `install.sh` ; si Whispy
  ne répond pas : notification « Whispy ne répond pas » et code de sortie non
  nul.
- **Service `systemd --user`** rattaché à `graphical-session.target` quand la
  session l'active (Wayland/Hyprland : l'environnement Wayland est alors
  présent), `default.target` sinon (X11 inchangé).
- Docs (README, install, dépannage, site) : Wayland/Omarchy documenté, « Wayland
  non supporté » retiré.

## Critères d'acceptation (Recette)

1. Dans la VM, F9 maintenu dans un terminal, une phrase en français, relâche :
   la phrase s'écrit ; `omarchy-default-dictation` = `whispy`, c'est Whispy qui
   transcrit (pas Voxtype). [à l'usage] pour la vraie voix ; prouvé avant la
   PR par une phrase synthétique jouée par le Mac.
2. Même geste dans un champ de Secrétaire (web app) : texte avec accents (é,
   è, à, ç) intacts.
4. Après redémarrage de la VM, Whispy répond seul sur `/status` (service
   systemd --user).
5. Whispy arrêté + F9 : une notification « Whispy ne répond pas », rien ne se
   perd en silence.
6. La phrase de test « Bonjour, je dicte une phrase en français pour tester la
   dictée dans Omarchy. » est transcrite en moins d'une seconde, à une erreur
   de mot près au plus.
7. Whispy macOS et X11 ne régressent pas : CI de Whispy verte.

(Le critère 3, la Régie, est livré à part ; il consomme `POST /transcribe`.)

Smoke : `curl -fsS -H "Authorization: Bearer $(cat ~/.config/whispy/config.token)" http://127.0.0.1:9090/status | grep -q model_loaded`
dans la VM après redémarrage.

## Raison d'être

Usage : l'utilisateur dicte au quotidien (plusieurs fois par jour) sur son
poste Omarchy. Sans : Voxtype + Whisper small, moins juste et plus lent.

## Refusé

- **Écoute evdev / groupe `input`** pour une hotkey dans Whispy : la liaison
  Hyprland existe déjà et ne demande aucun droit.
- **Tray sous Wayland** (pystray AppIndicator/SNI) : tirerait PyGObject et
  libayatana pour une icône ; les notifications suffisent.
- **Coller par Ctrl+V sous Wayland** : ignoré par les terminaux ; `wtype` tape
  le texte quelle que soit la disposition clavier.
- **V2 (Rust)** : plus tard.

## Coût

- Dépendances Python : aucune ajoutée. Outils système sous Wayland : `wtype`,
  `wl-copy` (déjà présents sous Omarchy), `notify-send`, `curl`.
- Réseau : aucun appel hors de 127.0.0.1.

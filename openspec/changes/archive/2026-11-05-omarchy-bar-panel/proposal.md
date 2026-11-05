## Why

On Omarchy (Hyprland, Wayland) Whispy has no tray and no overlay: state shows
only through notifications, settings need a hand-edited JSON file, and the
dictation key is a hand-written line in `~/.config/hypr/bindings.lua`.

**Need, in one sentence:** give Whispy on Omarchy what the macOS version has —
a bar icon with a settings panel, a dictation key picker, and the waveform
pill — for a user who dictates several times a day on this machine.

Framing decisions (validated by the user):
- Trigger picker = a short preset list: Right Option (hold), Right Ctrl
  (hold), F9 (hold), Left Option + Space (toggle).
- Pill = bottom centre, never takes keyboard focus (layer-shell overlay, no
  keyboard interactivity).
- Refused for now: the macOS sounds; capturing an arbitrary key (Wayland does
  not let an application read every key).

## What Changes

- **Omarchy bar widget** `whispy.panel` (`packaging/omarchy/whispy-panel/`,
  a Quickshell plugin modelled on the Superwhisper panel): the macOS braille
  waveform as the icon (still at rest, scrolling and green while listening,
  scrolling while transcribing, greyed with « Whispy stopped » when the daemon
  is down); a panel with the dictation key, model, language, copy to
  clipboard, start at login, the last dictation (click to copy), and an on/off
  switch plus « Start Whispy » when stopped; the waveform pill while
  recording.
- **`GET /level`**: `{"level": 0..1, "is_recording": bool}`, the live input
  level the pill polls while recording; successful polls are not logged.
- **`omarchy_trigger` config key** (choice of the four presets).
- **`omarchy-dictation-whispy trigger <preset>`**: saves the preset through
  `POST /config`, writes `~/.config/whispy/shortcuts.lua` (Omarchy's own hook
  for a dictation backend's bindings) and reloads Hyprland. `start`/`stop`
  nudge the widget over the shell's IPC so the icon follows a dictation
  without polling.
- **install.sh** links the plugin into `~/.config/omarchy/plugins` and puts it
  on the right of the bar.

## Acceptance criteria (Recette, the user's words)

1. À droite de la barre, l'icône Whispy passe en « écoute » quand je maintiens Option droite, en « transcription » au relâchement, puis redevient « prête ».
2. Un clic sur l'icône ouvre un panneau : modèle, langue, copie dans le presse-papiers, démarrage à l'ouverture de session, dernière dictée. Si je change la langue, la dictée suivante l'utilise, sans redémarrer.
3. Dans le panneau, je choisis « Ctrl droit (maintenir) » : Ctrl droit dicte aussitôt et Option droite ne dicte plus. Le choix tient après une reconnexion.
4. Je choisis « Option gauche + Espace (bascule) » : un appui démarre la dictée, un second l'arrête.
5. Pendant l'écoute, une pilule apparaît en bas au centre. Son onde bouge quand je parle et reste plate dans le silence. Le texte arrive dans la fenêtre où j'écris, qui garde le focus.
6. Si Whispy est arrêté, l'icône le montre (grisée, « Whispy arrêté ») et le panneau propose de le démarrer.
7. [à l'usage] Dans la VM, la pilule ne ralentit ni la dictée ni la frappe.

Criterion 2, language: Parakeet has no language setting (it detects the
language itself, and the macOS menu has no Language item either). The panel
shows Model and Language as information; the « next dictation uses it without
a restart » half is proven with Copy to clipboard, the live setting that
exists. See design.md, D7.

Smoke (after merge, on the VM):
`curl -fsS -H "Authorization: Bearer $(cat ~/.config/whispy/config.token)" http://127.0.0.1:9090/level | grep -q '"level"'`
and `omarchy-shell whispy state` answers `ready`.

## Impact

- `src/whispy/api/server.py`, `src/whispy/core/config.py`
- `packaging/omarchy/omarchy-dictation-whispy`, new `packaging/omarchy/whispy-panel/`
- `install.sh`, docs (`docs/src/install.html`, `usage.html`), `website/index.html`, `FEATURE_MATRIX.md`
- No new runtime dependency (Quickshell and `wl-copy` ship with Omarchy).

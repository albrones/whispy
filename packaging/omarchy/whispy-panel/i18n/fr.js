// The Omarchy panel's texts in French. en.js has the same keys
// (tests/test_omarchy_panel_model.py fails otherwise); Model.lang() picks one.
var TEXTS = {
  "phase.ready": "Prêt",
  "phase.recording": "À l'écoute",
  "phase.transcribing": "Transcription",
  "phase.loading": "Chargement du modèle",
  "phase.no_model": "Modèle non chargé",
  "phase.stopped": "Whispy arrêté",
  "phase.yielded": "Une ancienne version de Whispy est ouverte",
  "preset.right_option_hold": "Option droite (maintenir)",
  "preset.right_ctrl_hold": "Ctrl droite (maintenir)",
  "preset.f9_hold": "F9 (maintenir)",
  "preset.left_option_space_toggle": "Option gauche + Espace (bascule)",
  "start": "Démarrer Whispy",
  "start.busy": "Démarrage de Whispy…",
  "start.caption": "Lance systemctl --user start whispy2",
  "starting": "Démarrage",
  "stopping": "Arrêt",
  "dictation_key": "Touche de dictée",
  "dictation_key.default": "Celle d'Omarchy",
  "model": "Modèle",
  "language": "Langue dictée",
  "language.value": "Détectée automatiquement",
  "start_at_login": "Ouvrir à la connexion",
  "update.caption": "L'installe, puis redémarre Whispy",
  "last_dictation": "DERNIÈRE DICTÉE",
  "last_dictation.none": "Rien dicté pour l'instant",
  "last_dictation.copy": "Clic ou C pour copier",
  "copied": "Copié",
  "error.key": "Impossible de changer la touche",
  "error.login": "Impossible de changer l'ouverture à la connexion",
  "error.service": "systemctl n'a pas pu changer l'état de Whispy"
}

if (typeof module !== "undefined") module.exports = { TEXTS: TEXTS }

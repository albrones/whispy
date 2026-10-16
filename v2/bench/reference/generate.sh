#!/usr/bin/env bash
# Regenerate the bench's reference clips: synthetic voices (macOS `say`), not
# recordings. They give the bench a known text for the word error rate; the
# real dictations are the lost clips in ~/.whispy/lost/.
#
# `say` is not byte-stable between runs, so the WAVs are committed and this
# script only documents how they were made. Run from anywhere on macOS:
#   bash v2/bench/reference/generate.sh
#
# Keep manifest.tsv in sync: one line per clip, <file> <lang> <kind> <text>.
set -euo pipefail
cd "$(dirname "$0")"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Columns: file, voice, kind, text. kind is short (a few words), sentence
# (about 5 s, the latency target) or long (10 s and more).
clips=(
  "fr-short-ameliorer|Thomas|short|à améliorer, je pense"
  "fr-short-daccord|Thomas|short|d'accord"
  "fr-short-merci|Thomas|short|merci beaucoup"
  "fr-short-demain|Thomas|short|on verra demain"
  "fr-short-parfait|Thomas|short|c'est parfait"
  "fr-short-ameliorer-jacques|Jacques|short|à améliorer, je pense"
  "fr-short-rappelle-jacques|Jacques|short|rappelle-moi plus tard"
  "fr-short-oui-jacques|Jacques|short|oui, vas-y"
  "fr-sentence-rapport|Thomas|sentence|je vais envoyer le rapport à l'équipe demain matin avant la réunion"
  "fr-sentence-courses|Thomas|sentence|pense à acheter du pain et des tomates en rentrant ce soir"
  "fr-sentence-train-jacques|Jacques|sentence|le train de huit heures est annulé, je prendrai le suivant"
  "fr-sentence-mixed|Thomas|sentence|je dois pousser la branche sur GitHub avant la revue de code"
  "fr-long-projet|Thomas|long|nous avons terminé la première version du projet la semaine dernière, mais il reste plusieurs problèmes à corriger avant de la présenter aux utilisateurs, notamment la vitesse et la fiabilité de la transcription"
  "fr-long-vacances|Thomas|long|pour les vacances, nous pensons partir en Bretagne au mois d'août, louer une petite maison près de la mer et faire de longues promenades à vélo le long de la côte"
  "en-short-sounds-good|Samantha|short|sounds good"
  "en-short-thanks|Samantha|short|thank you"
  "en-short-check|Samantha|short|let me check"
  "en-short-not-today|Samantha|short|not today"
  "en-short-later-daniel|Daniel|short|talk to you later"
  "en-short-perfect-daniel|Daniel|short|that is perfect"
  "en-sentence-report|Samantha|sentence|I will send the report to the team tomorrow morning before the meeting"
  "en-sentence-groceries|Samantha|sentence|remember to buy bread and tomatoes on your way home tonight"
  "en-sentence-train-daniel|Daniel|sentence|the eight o'clock train is cancelled so I will take the next one"
  "en-long-project|Samantha|long|we finished the first version of the project last week, but several problems remain to be fixed before we show it to users, especially the speed and the reliability of the transcription"
  "en-long-holidays|Samantha|long|for the holidays we are thinking of going to the coast in August, renting a small house near the sea and taking long bike rides along the shore"
)

: > manifest.tsv
for entry in "${clips[@]}"; do
  IFS='|' read -r name voice kind text <<<"$entry"
  lang="${name%%-*}"
  say -v "$voice" "$text" -o "$work/$name.aiff"
  afconvert "$work/$name.aiff" -f WAVE -d LEI16@16000 -c 1 "$name.wav"
  printf '%s\t%s\t%s\t%s\n' "$name.wav" "$lang" "$kind" "$text" >> manifest.tsv
done

# V1's committed validation clips (tests/fixtures/audio, also `say`) ride along.
printf '%s\t%s\t%s\t%s\n' "../../../tests/fixtures/audio/fr_speech.wav" fr sentence "test un deux trois, le test est fini" >> manifest.tsv
printf '%s\t%s\t%s\t%s\n' "../../../tests/fixtures/audio/en_speech.wav" en sentence "testing one two three, the test is done" >> manifest.tsv
echo "Regenerated $(wc -l < manifest.tsv | tr -d ' ') reference clips"

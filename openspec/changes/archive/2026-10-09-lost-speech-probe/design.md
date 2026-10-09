# Lost speech — diagnosis

Measured on 2026-10-09 on the 20 clips Whispy kept in `~/.whispy/lost/` after PR #24 (the cap). Between the reinstall and the measurement the log counted 97 successful transcriptions and 35 `Lost speech` warnings.

## Method

Each clip was replayed with `scripts/replay_lost.py` (Parakeet, as Whispy runs it) under four variants, then transcribed by a second, independent model — Whisper small, French, beam 5, no VAD, in a throwaway venv — to tell real speech from noise without listening. A clip counts as **speech** when Whisper is confident (`no_speech_prob` < 0.2 and `avg_logprob` > −0.5). Below that, Whisper either returns nothing or its known silence hallucinations ("Sous-titres réalisés par la communauté d'Amara.org", low-confidence "C'est bon").

## Results

| clip | RMS | crest | Whisper verdict | untouched | Whispy trim | 1 s margin | peak-normalized | RMS 0.05 |
|---|---|---|---|---|---|---|---|---|
| 151249 | 0.0018 | 33 | noise ("C'est bon", nsp 0.40, lp −1.14) | – | – | – | – | – |
| 151253 | 0.0050 | 30 | noise ("C'est bon.", 0.50, −1.21) | – | – | – | – | – |
| 151257 | 0.0063 | 39 | noise | – | – | – | – | – |
| 152820 | 0.0118 | 7.5 | **speech** (0.06, −0.20) | – | – | – | text | **text** |
| 154746 | 0.0134 | 10 | **speech** (0.06, −0.32) | – | – | – | text | **text** |
| 154812 | 0.0032 | 11 | nothing | – | – | – | – | – |
| 154820 | 0.0039 | 30 | noise (0.55, −1.35) | – | – | – | "Uh" | "Uh" |
| 154827 | 0.0046 | 91 | nothing | – | – | – | – | – |
| 154830 | 0.0034 | 51 | nothing | – | – | – | – | – |
| 154856 | 0.0154 | 13 | noise ("Bonne soirée.", 0.47, −1.20) | – | – | – | – | – |
| 154901 | 0.0354 | 28 | nothing | – | – | – | – | – |
| 154908 | 0.0075 | 9 | hallucination (Amara.org) | – | – | – | – | – |
| 154915 | 0.0032 | 7.5 | nothing | – | – | – | – | – |
| 154922 | 0.0033 | 11 | hallucination (Amara.org) | – | – | – | – | – |
| 185834 | 0.0027 | 25 | hallucination (Amara.org) | – | – | – | – | – |
| 190814 | 0.0104 | 7.4 | **speech** (0.08, −0.49) | – | – | – | – | **text** |
| 190913 | 0.0122 | 6.3 | **speech** (0.18, −0.28) | – | text | – | text | **text** |
| 192025 | 0.0114 | 6.3 | doubtful ("que je crois que de toute façon", 0.41, −0.93) | – | – | – | – | – |
| 192050 | 0.0028 | 7.1 | nothing | – | – | – | – | – |
| 192118 | 0.0018 | 42 | hallucination (Amara.org) | – | – | – | – | – |

RMS is the whole clip after DC removal; crest is peak / RMS (clicks and taps read 25–90, steady voice 6–13).

## Cause

Two populations hide behind the one warning:

1. **Three quarters are not speech.** 15 of 20 clips are clicks, taps, breath or room noise that cleared the voiced-duration gate (0.4–1.6 s "voiced"). The model is right to return nothing; the warning's name overstates them. Nothing was lost.
2. **The real losses are quiet dictation.** The 4 clips Whisper hears clearly — plus the doubtful fifth — all sit at RMS 0.010–0.013, an order of magnitude below the 0.147 the transcription-quality spec measured for real utterances. Parakeet returns empty on speech that quiet. Trimming is not the cause: the trimmed, untrimmed and 1 s-margin copies rescue at most 1 of the 4. Loudness is: scaled to RMS 0.05, all 4 come back as the right sentence.

## Fix

When both existing calls come back empty, Whispy now tries a third time on the original scaled to RMS 0.05 (`LOUDNESS_RETRY_RMS`), and skips it for clips already that loud. Target sweep on the same 20 clips through the full `transcribe` path:

| target | clear speech recovered | fillers on the 15 non-speech clips |
|---|---|---|
| 0.03 | 2 / 4 (one mixed with English) | 0 |
| 0.04 | 4 / 4 | 1 ("Uh") |
| 0.05 | **4 / 4** | 1 ("Uh") |

0.05 recovers the 4 at the best transcription quality. The single "Uh" is the known filler failure; for scale, the existing untrimmed retry produced 7 real rescues and 5 fillers ("Yeah.", "Thank you.", "Mm-hmm."…) across its 98 attempts in the log. A filler blocklist stays excluded (see transcription-quality: "Okay." and "No." are real dictations).

## Acceptance criterion 5, restated by measurement

As written, "text for at least 80% of the kept clips" assumed every kept clip was speech; with 15 of 20 being noise, meeting it would mean typing hallucinations. It is measured instead on the clips that hold speech: **4 / 4 clear (100%), 4 / 5 counting the doubtful one (80%)**. All 20 together: 5 / 20 return text (4 sentences + "Uh").

## Left open

- `Lost speech` still fires for noise, so criterion 6's ratio counts noise as losses. Telling the two apart in the warning would need a second model or a crest/RMS rule that this data (20 clips) is too thin to set.
- Why the dictation is that quiet (mic distance, input gain, device) is outside Whispy; card #145 covers the related "microphone hears nothing" case.

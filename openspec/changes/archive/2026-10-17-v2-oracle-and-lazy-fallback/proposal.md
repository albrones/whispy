## Why

The first bench (change `v2-engines-and-bench`) left two card criteria open
(Régie card whispy #1): 5 of 20 lost clips recovered against 70 % asked, and
1.72 GB with Parakeet and whisper both loaded against 1.5 GB. The user then
reframed both (card thread, 2026-10-17):

- **Criterion 3**: ≥ 70 % of the lost clips **that really hold speech**,
  checked by a larger local reference model, then by ear for the doubtful ones.
  V1 also lost breath and silence; no engine should type anything for those.
- **Criterion 5**: ≤ 1.5 GB **outside a reprise**: whisper is loaded only
  when Parakeet returns nothing, and freed after 30 s idle; the cost of a
  reprise is measured, not hidden.

**Need, in one sentence:** know how much real speech V2 recovers, and keep its
everyday memory under 1.5 GB without giving up the whisper fallback.

## What Changes

- `whispy-core`: `Lazy`, a `Transcriber` that loads its engine on the first
  call and frees it after `FALLBACK_IDLE` (30 s) without a call, through a
  short-lived thread that exists only while the engine is loaded.
  `EngineKind::lazy` checks the model file up front. `Pipeline::load_default`
  now builds whisper as a lazy fallback; its signature and `transcribe` are
  unchanged for the app.
- `v2/bench/oracle.py`: whisper large-v3-turbo (MLX, already on the Mac) in a
  throwaway venv classes each lost clip speech / doubtful / no speech, copies
  the clips and writes `listen.html` to settle the doubtful ones by ear. All
  of it lands in the gitignored `v2/bench/oracle/`.
- `banc`: reads the oracle's classes and the user's verdicts, adds « lost
  speech: text » and « WER vs oracle » columns, uses them first when picking,
  and replaces the eager « both engines loaded » memory probe with a probe of
  the default pipeline: 180 s dictation, two reprises, 32 s of quiet.

## Raison d'être

- **Usage**: the user dictates daily; a miss (Parakeet empty) happens a few
  times a day. Memory is held all day, a reprise lasts a second.
- **Without it**: either 1.7 GB held all day, or Parakeet alone and the
  « à améliorer, je pense » misses come back.

## Refusé

- **Shipping the larger model**: 1.6 GB on its own, it is the referee only.
- **A smaller whisper (base/tiny) as fallback**: not measured on the lost
  clips; the lazy load already meets the budget.
- **Committing the oracle's labels**: they sit next to the user's words; the
  report carries counts and classes only.

## Coût

- No new Rust dependency. The oracle venv (`mlx-audio`) is a bench tool,
  outside the repository and the app.
- No network at run time: models already on the Mac, `HF_HUB_OFFLINE=1`.
- Reprise: whisper load ~0.25 s added on the first one (measured), ~0.7 GB
  more for up to 30 s.

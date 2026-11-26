## Why

Card 2/3 of the Linux switch to V2 (albrones/whispy#53). On Omarchy, V1 plugs
into the bar (panel, recording pill) and the dictation keys through its HTTP
API on `:9090`. V2 opens no network port: everything must go through its
control socket (`~/.whispy/v2/control.sock`).

## What Changes

- **V2 control socket**: `status` carries the input `level` (V1's scale, 0
  when nothing records); a new `last` request answers the whole text of the
  last dictation, kept in memory only, never on disk. `whispy2 send <request>`
  is a one-shot client, so scripts need no `socat` or `nc`.
- **Omarchy dictation backend** (`omarchy-dictation-whispy`): `start`, `stop`,
  `toggle` call `whispy2 send`; no curl, no token, no V1. Failure, refusal or a
  missing `whispy2` posts « Whispy is not answering ». `trigger <preset>` saves
  `omarchy_trigger` in `config.json` with `jq` (no running Whispy needed), then
  writes `shortcuts.lua` and reloads Hyprland as before.
- **Bar panel** (`whispy-panel/Service.qml`): reads the socket with
  Quickshell's `Socket` (one connection per request): `status` for the icon and
  the pill's level (every 50 ms while listening), `last` for the last
  dictation. The key is read from `config.json` (`FileView`).
- **Removed from the panel** (Alexis' choice): Copy to clipboard (Linux V2
  always types), Start at login and Start Whispy (they come back with the V2
  Linux service, card 3/3), the power switch.
- Clean switch (Alexis' choice): no HTTP fallback to V1; card 3/3 removes V1.

## Impact

- Specs: `v2-app-control` (protocol), `linux-support` (Omarchy backend, key
  presets, bar widget, pill).
- Proof: `v2/whispy2/linux-e2e/omarchy.sh`, in its own image
  (`linux-e2e/omarchy/Dockerfile`: Quickshell 0.3.2 built from source).

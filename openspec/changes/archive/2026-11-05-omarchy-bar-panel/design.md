## Context

Under Wayland Whispy runs headless (`systemd --user`), driven by Hyprland
through `omarchy-dictation-whispy`. The Omarchy shell is one long-running
Quickshell process that loads third-party bar widgets from
`~/.config/omarchy/plugins/<dir>/manifest.json`. The reference is the
installed Superwhisper panel.

## Decisions

**D1. One Quickshell plugin, three parts.** `Panel.qml` (bar icon + panel),
`Service.qml` (talks to the daemon), `Pill.qml` (overlay), `Model.js` (pure
logic, tested under node). Shipped in the repo, symlinked by `install.sh` so
it follows the checkout like the backend script.

**D2. The API is read with QML's XMLHttpRequest, not curl.** Checked on the
VM: QML's XHR sends neither `Origin` nor `Referer`, so it passes the API's
browser guard with the bearer token read from `config.token` (FileView). A
poll costs one loopback request and no process spawn.

**D3. When the widget asks.** At rest: one `/status` every 30 s — the only
way to notice a daemon that died on its own; cost is negligible. On a nudge:
`omarchy-dictation-whispy start|stop` call `omarchy-shell -q whispy
refresh|transcribing` in the background, so the icon follows a dictation at
once. While Whispy works (recording, transcribing, loading, starting):
`/status` every 500 ms. While the pill shows: `/level` every 50 ms, one
request in flight at most. Rejected: polling `/status` fast all the time
(background work for nothing); a push channel from the daemon (new server
machinery for one consumer).

**D4. Transcribing needs a hint.** The API server is serial and `/stop` is
synchronous: while it runs, `/status` waits behind it. The backend therefore
says `transcribing` over IPC before calling `/stop`; the hint holds while
`/status` still says recording or transcribing and is dropped by the first
idle answer (65 s safety deadline). Making the server threaded was rejected:
it changes concurrency for every client to serve one icon.

**D5. `GET /level`.** A dedicated endpoint returning one float (0 when not
recording), rather than a field on `/status` which also serialises the FSM.
Successful `/level` requests are not logged (20 lines a second otherwise).

**D6. The pill.** A small `PanelWindow` (168×52, the macOS size), layer
`Overlay`, `keyboardFocus: None`, empty input `mask`, anchored bottom with a
40 px margin, on the focused monitor only. Bars, envelope, wobble, colours and
the γ 0.5 × 2 boost mirror `waveform_window.py`. The level is gated at 0.05
(the transcription silence gate, RMS 0.005 × 10) so the wave is flat in
silence. A small surface rather than Omarchy's fullscreen `OverlayWindow`,
to keep compositing cheap in a VM (criterion 7).

**D7. Model and Language are information.** Parakeet ships in one size and
detects the language itself; `onnx_asr` only accepts a language for Whisper
and Canary models, and the macOS menu dropped both items for this reason. The
panel shows « Parakeet TDT 0.6B v3 » and « Detected automatically » instead of
choices that would set nothing. Criterion 2's live-change half is proven with
Copy to clipboard. Assumption recorded for the user to confirm.

**D8. The trigger file is Omarchy's backend hook.** Omarchy's
`default/hypr/dictation-backend.lua` dofiles
`~/.config/<backend>/shortcuts.lua` after its default dictation keys while
that backend is selected. `trigger <preset>` writes
`~/.config/whispy/shortcuts.lua`: it `hl.unbind`s every preset key (`ALT +
SPACE`, `ALT + Alt_R`, `Alt_R`, `ISO_Level3_Shift`, `Control_R`, `F9`), then
binds the chosen one, and runs `hyprctl reload`. Install needs no edit of the
user's `bindings.lua`; a hand-written dictation line there (loaded later)
still wins, so on this machine the right-Option and F9 lines were removed
from `bindings.lua` (Super+Ctrl+X kept). Hold presets are `bind_hold` with
`ignore_mods` and `non_consuming`, so AltGr characters and Ctrl shortcuts keep
working. Right Option binds both `ISO_Level3_Shift` (AltGr layouts such as
French Macintosh) and `Alt_R` (US). The preset is saved first through `POST
/config` (`omarchy_trigger`): with the daemon down nothing changes. Without a
file, Omarchy's defaults apply (Right Alt hold + Alt+Space toggle), which the
config default `right_option_hold` approximates.

**D9. Start at login is the systemd unit's enablement** (`systemctl --user
is-enabled|enable|disable whispy`), read when the panel opens. The
`start_at_login` key stays macOS-only. The on/off switch and « Start Whispy »
run `systemctl --user start|stop whispy` (after `reset-failed`).

**D10. Placement.** `bar.layout.right`, next to the tray drawer, not inside
`bar.tray`: the drawer is collapsed, and criterion 1 asks for the icon to be
seen on the right of the bar.

## Risks

- Several monitors = one widget (and one poller) per bar; the pill shows on
  the focused monitor only. Acceptable at one poll per 30 s.
- A daemon wedged without closing its socket leaves the last state shown.
- Keyboard-only criteria (1, 3, 4) and the real-voice half of 5 need a person
  at the keyboard; they are manual-ui rows.

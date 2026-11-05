## 1. Daemon

- [x] 1.1 `GET /level` (clamped 0..1, 0 when idle), successful polls not logged
- [x] 1.2 `omarchy_trigger` config key with the four presets

## 2. Omarchy backend

- [x] 2.1 `trigger <preset>`: save through `/config`, write `~/.config/whispy/shortcuts.lua`, `hyprctl reload`; unknown preset rejected, daemon down changes nothing
- [x] 2.2 `start`/`stop` nudge the bar widget over IPC (`refresh`, `transcribing`)

## 3. Bar widget

- [x] 3.1 `whispy.panel` plugin: icon states, panel (key, model, language, clipboard, start at login, last dictation, start/stop)
- [x] 3.2 Waveform pill (overlay, no keyboard focus, click-through)
- [x] 3.3 `install.sh` links the plugin and puts it on the bar; uninstall removes the link

## 4. Tests, docs

- [x] 4.1 Unit tests: `/level`, config key, backend `trigger`, `Model.js` under node, install script
- [x] 4.2 FEATURE_MATRIX rows (unit + manual-ui), docs (`make docs`), website
- [x] 4.3 Live proof on the Omarchy VM (screenshots, `hyprctl binds`, `hyprctl configerrors`, shell logs)

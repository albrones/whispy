"""Pure logic of the Omarchy bar widget (packaging/omarchy/whispy-panel/Model.js).

The QML has no test harness here; its decisions live in Model.js, which runs
under node when it is available. The preset list is also checked against the
config schema without node, since a drift there breaks the trigger picker.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / "packaging" / "omarchy" / "whispy-panel"
MODEL = PLUGIN / "Model.js"
I18N = PLUGIN / "i18n"
BACKEND = ROOT / "packaging" / "omarchy" / "omarchy-dictation-whispy"
SCHEMA = json.loads((ROOT / "docs" / "src" / "config-schema.json").read_text(encoding="utf-8"))
OMARCHY_TRIGGER_PRESETS = tuple(SCHEMA["omarchy_trigger"]["choices"])

NODE_SCRIPT = r"""
const m = require(process.argv[1]);
const en = require(process.argv[2]).TEXTS;
const fr = require(process.argv[3]).TEXTS;
const ready = {state: "idle", models_loaded: true, yielded: false, last_problem: null, trigger_mode: "hold", level: 0};
const out = {
  stopped: m.phase(false, null),
  ready: m.phase(true, ready),
  recording: m.phase(true, {...ready, state: "recording", level: 0.4}),
  transcribing: m.phase(true, {...ready, state: "transcribing"}),
  inserting: m.phase(true, {...ready, state: "inserting"}),
  yielded: m.phase(true, {...ready, state: "yielded", yielded: true}),
  loading: m.phase(true, {...ready, models_loaded: false}),
  noModel: m.phase(true, {...ready, models_loaded: false, last_problem: "The models could not be loaded"}),
  yieldedLabel: m.phaseLabel("yielded", en),
  yieldedIsRest: m.isActive("yielded"),
  stoppedTooltip: m.tooltip("stopped", en),
  listeningTooltip: m.tooltip("recording", en),
  frenchTooltip: m.tooltip("recording", fr),
  frenchStopped: m.phaseLabel("stopped", fr),
  frenchPresets: m.presets(fr).map(p => p.label),
  langs: {
    appFrench: m.lang({...ready, lang: "fr"}, {language: "en"}, "en_US.UTF-8"),
    appEnglish: m.lang({...ready, lang: "en"}, {}, "fr_FR.UTF-8"),
    oldApp: m.lang(ready, {}, "fr_FR.UTF-8"),
    stoppedForced: m.lang(null, {language: "en"}, "fr_FR.UTF-8"),
    stoppedSystem: m.lang(null, {language: "system"}, "fr_CA.UTF-8"),
    stoppedOther: m.lang(null, {}, "de_DE.UTF-8"),
    noLocale: m.lang(null, null, ""),
    notFrench: m.lang(null, {}, "fy_NL.UTF-8"),
  },
  enKeys: Object.keys(en).sort(),
  frKeys: Object.keys(fr).sort(),
  enEmpty: Object.keys(en).filter(k => !en[k]),
  frEmpty: Object.keys(fr).filter(k => !fr[k]),
  idleFrames: [m.frame("ready", 0), m.frame("ready", 5), m.frame("stopped", 3)],
  activeFrames: [m.frame("recording", 0), m.frame("recording", 1), m.frame("transcribing", 16)],
  silence: [m.displayLevel(0), m.displayLevel(0.05), m.displayLevel(NaN)],
  speech: [m.displayLevel(0.1), m.displayLevel(0.3), m.displayLevel(5)],
  flatBars: [0, 5, 10].map(i => m.barHeight(i, 11, 0, 1.3, 5, 38)),
  loudCentre: m.barHeight(5, 11, 1, Math.PI / 2 - 4.5, 5, 38),
  loudEdge: m.barHeight(0, 11, 1, Math.PI / 2, 5, 38),
  presets: m.PRESETS.map(p => p.value),
  labels: m.PRESETS.map(p => m.presetLabel(p.value, en)),
  unknownLabel: m.presetLabel("caps_lock_hold", en),
  updateStopped: m.updateRow(false, null),
  updateOld: m.updateRow(true, ready),
  updateOffer: m.updateRow(true, {...ready, update: {title: "Update available (2.5.0)", action: "update", transient: false}}),
  updateLine: m.updateRow(true, {...ready, update: {title: "Whispy 2.6.0 · up to date", action: null, transient: false}}),
  updateBusy: m.updateRow(true, {...ready, update: {title: "Updating to 2.5.0…", action: null, transient: true}}),
  updateBogus: m.updateRow(true, {...ready, update: {title: "x", action: "rm -rf", transient: "yes"}}),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def model() -> dict:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    result = subprocess.run(
        ["node", "-e", NODE_SCRIPT, str(MODEL), str(I18N / "en.js"), str(I18N / "fr.js")],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_phase_follows_the_v2_status(model):
    assert model["stopped"] == "stopped"
    assert model["ready"] == "ready"
    assert model["recording"] == "recording"
    assert model["transcribing"] == "transcribing"
    # Typing the text is still the end of the dictation, not rest.
    assert model["inserting"] == "transcribing"
    assert model["yielded"] == "yielded"
    assert model["yieldedLabel"] == "An older Whispy is running"
    assert model["yieldedIsRest"] is False
    assert model["loading"] == "loading"
    assert model["noModel"] == "no-model"


def test_tooltips_name_the_state(model):
    assert model["stoppedTooltip"] == "Whispy stopped"
    assert model["listeningTooltip"] == "Whispy · Listening"


def test_the_panel_speaks_whispys_language_else_the_configs_else_the_sessions(model):
    langs = model["langs"]
    # Running, Whispy says which language is in force, a menu choice included.
    assert langs["appFrench"] == "fr"
    assert langs["appEnglish"] == "en"
    # Stopped (or too old to say): the forced language, else the locale.
    assert langs["oldApp"] == "fr"
    assert langs["stoppedForced"] == "en"
    assert langs["stoppedSystem"] == "fr"
    assert langs["stoppedOther"] == "en"
    assert langs["noLocale"] == "en"
    assert langs["notFrench"] == "en"
    assert model["frenchTooltip"] == "Whispy · À l'écoute"
    assert model["frenchStopped"] == "Whispy arrêté"
    assert model["frenchPresets"][0] == "Option droite (maintenir)"


def test_both_panel_translation_files_have_every_text(model):
    assert model["enKeys"] == model["frKeys"], "i18n/en.js and i18n/fr.js disagree"
    assert model["enEmpty"] == [] and model["frEmpty"] == []


def test_every_text_the_panel_draws_is_in_the_translation_files():
    """Without node: each Model.text(…, "key") and preset label resolves in both files."""
    keys = {
        name: set(re.findall(r'^\s*"([a-z0-9_.]+)":', (I18N / f"{name}.js").read_text(encoding="utf-8"), re.MULTILINE))
        for name in ("en", "fr")
    }
    assert keys["en"] == keys["fr"], "i18n/en.js and i18n/fr.js disagree"
    used = set()
    for path in [*PLUGIN.glob("*.qml"), MODEL]:
        used |= set(re.findall(r'Model\.text\([^,]+, "([a-z0-9_.]+)"\)', path.read_text(encoding="utf-8")))
        used |= set(re.findall(r'text\(t, "([a-z0-9_.]+)"\)', path.read_text(encoding="utf-8")))
    used |= {f"preset.{value}" for value in OMARCHY_TRIGGER_PRESETS}
    assert used, "no text found"
    assert used <= keys["en"], f"missing: {sorted(used - keys['en'])}"
    # The ternary in the start row names its two keys outside a Model.text call.
    assert {"start", "start.busy"} <= keys["en"]


def test_icon_rests_still_and_scrolls_while_working(model):
    idle = model["idleFrames"]
    assert len(set(idle)) == 1
    active = model["activeFrames"]
    assert active[0] != active[1]
    assert active[0] == active[2]  # 16 frames, wrapping


def test_wave_is_flat_in_silence_and_moves_with_speech(model):
    assert model["silence"] == [0, 0, 0]
    quiet, normal, loud = model["speech"]
    assert 0 < quiet < normal <= loud == 1
    assert model["flatBars"] == [5, 5, 5]
    assert model["loudCentre"] > model["loudEdge"] > 5


def test_the_update_row_comes_from_the_status_and_names_its_request(model):
    assert model["updateStopped"] is None
    assert model["updateOld"] is None, "a Whispy without the field shows no row"
    assert model["updateOffer"] == {"title": "Update available (2.5.0)", "request": "update", "transient": False}
    assert model["updateLine"] == {"title": "Whispy 2.6.0 · up to date", "request": "", "transient": False}
    assert model["updateBusy"] == {"title": "Updating to 2.5.0…", "request": "", "transient": True}
    # Only the known request is ever sent.
    assert model["updateBogus"] == {"title": "x", "request": "", "transient": False}


def test_the_panel_sends_only_the_update_request_whispy_knows():
    service = (PLUGIN / "Service.qml").read_text()
    assert 'request: "update"' in service
    assert "check-update" not in service, "the panel has no check button: Whispy checks on its own"
    assert "root.update.transient" in service
    panel = (PLUGIN / "Panel.qml").read_text()
    assert 'rowId: "update"' in panel and "sw.runUpdate()" in panel
    # The grey version line is shown but can be neither clicked nor reached
    # with the keyboard: only a row with a request can.
    assert 'actionable: sw.update !== null && sw.update.request === "update"' in panel
    assert 'sw.update !== null && sw.update.request === "update" ? ["update"]' in panel
    assert "enabled: actionRow.actionable" in panel


def test_presets_match_the_config_schema(model):
    assert tuple(model["presets"]) == OMARCHY_TRIGGER_PRESETS
    assert all(model["labels"])
    assert model["unknownLabel"] == ""


def test_backend_presets_match_the_config_schema():
    """Without node: the backend's list, the panel's and the schema agree."""
    backend = re.search(r"^presets=\(([^)]*)\)", BACKEND.read_text(encoding="utf-8"), re.MULTILINE)
    assert backend is not None
    assert tuple(backend.group(1).split()) == OMARCHY_TRIGGER_PRESETS
    panel = re.findall(r'value: "([a-z0-9_]+)"', MODEL.read_text(encoding="utf-8"))
    assert tuple(panel) == OMARCHY_TRIGGER_PRESETS
    assert SCHEMA["omarchy_trigger"]["default"] == OMARCHY_TRIGGER_PRESETS[0]


def test_plugin_text_is_never_rich_text():
    """Text bound to daemon data (the last dictation) must not render markup."""
    for qml in PLUGIN.glob("*.qml"):
        source = qml.read_text()
        texts = len(re.findall(r"^\s*Text \{", source, re.MULTILINE))
        plain = source.count("textFormat: Text.PlainText")
        assert plain >= texts, f"{qml.name}: {texts} Text items, {plain} PlainText"


def test_manifest_points_at_the_entry_point():
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == "whispy.panel"
    assert (PLUGIN / manifest["entryPoints"]["barWidget"]).is_file()


def test_the_panel_reads_the_v2_socket_and_no_network_port():
    """Whispy V2 opens no port: the panel talks to its control socket only."""
    for path in [*PLUGIN.glob("*.qml"), MODEL]:
        source = path.read_text()
        for gone in ("XMLHttpRequest", "http://", "9090", "config.token"):
            assert gone not in source, f"{path.name} still uses {gone}"
    service = (PLUGIN / "Service.qml").read_text()
    assert "/.whispy/v2/control.sock" in service
    assert 'request: "status"' in service and 'request: "last"' in service


def test_the_panel_drives_the_v2_unit():
    """The power switch and Start at login act on whispy2.service, never V1's unit."""
    service = (PLUGIN / "Service.qml").read_text()
    assert 'readonly property string unit: "whispy2.service"' in service
    assert '"--user", "is-enabled", root.unit' in service
    assert 'on ? "enable" : "disable", unit' in service
    assert 'exec "$0" --user start "$1"' in service and '"--user", "stop", unit' in service
    # After a stop, the status is read until Whispy is gone, not once.
    assert "running: root.active || root.starting || root.stopping" in service
    assert "else stopping = false" in service
    assert '"whispy"]' not in service, "V1's unit name"
    panel = (PLUGIN / "Panel.qml").read_text()
    assert 'rowId: "start"' in panel and 'rowId: "login"' in panel
    assert "id: powerSwitch" in panel
    assert "sw.setRunning(!sw.reachable && !sw.starting)" in panel
    assert "sw.setStartAtLogin(!sw.startAtLogin)" in panel

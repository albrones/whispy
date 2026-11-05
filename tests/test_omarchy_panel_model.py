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

from whispy.core.config import OMARCHY_TRIGGER_PRESETS

PLUGIN = Path(__file__).parent.parent / "packaging" / "omarchy" / "whispy-panel"
MODEL = PLUGIN / "Model.js"

NODE_SCRIPT = r"""
const m = require(process.argv[1]);
const ready = {is_recording: false, is_transcribing: false, model_loading: false, model_loaded: true};
const out = {
  stopped: m.phase(false, null, false),
  ready: m.phase(true, ready, false),
  recording: m.phase(true, {...ready, is_recording: true}, false),
  // The backend says /stop is running while /status still says recording.
  hinted: m.phase(true, {...ready, is_recording: true}, true),
  transcribing: m.phase(true, {...ready, is_transcribing: true}, false),
  loading: m.phase(true, {...ready, model_loaded: false, model_loading: true}, false),
  noModel: m.phase(true, {...ready, model_loaded: false}, false),
  stoppedTooltip: m.tooltip("stopped"),
  listeningTooltip: m.tooltip("recording"),
  idleFrames: [m.frame("ready", 0), m.frame("ready", 5), m.frame("stopped", 3)],
  activeFrames: [m.frame("recording", 0), m.frame("recording", 1), m.frame("transcribing", 16)],
  silence: [m.displayLevel(0), m.displayLevel(0.05), m.displayLevel(NaN)],
  speech: [m.displayLevel(0.1), m.displayLevel(0.3), m.displayLevel(5)],
  flatBars: [0, 5, 10].map(i => m.barHeight(i, 11, 0, 1.3, 5, 38)),
  loudCentre: m.barHeight(5, 11, 1, Math.PI / 2 - 4.5, 5, 38),
  loudEdge: m.barHeight(0, 11, 1, Math.PI / 2, 5, 38),
  presets: m.PRESETS.map(p => p.value),
  labels: m.PRESETS.map(p => m.presetLabel(p.value)),
  unknownLabel: m.presetLabel("caps_lock_hold"),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def model() -> dict:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    result = subprocess.run(["node", "-e", NODE_SCRIPT, str(MODEL)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_phase_follows_the_daemon(model):
    assert model["stopped"] == "stopped"
    assert model["ready"] == "ready"
    assert model["recording"] == "recording"
    assert model["hinted"] == "transcribing"
    assert model["transcribing"] == "transcribing"
    assert model["loading"] == "loading"
    assert model["noModel"] == "no-model"


def test_tooltips_name_the_state(model):
    assert model["stoppedTooltip"] == "Whispy stopped"
    assert model["listeningTooltip"] == "Whispy · Listening"


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


def test_presets_match_the_config_schema(model):
    assert tuple(model["presets"]) == OMARCHY_TRIGGER_PRESETS
    assert all(model["labels"])
    assert model["unknownLabel"] == ""


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

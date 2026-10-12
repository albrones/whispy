"""Guards for the docs widgets (docs/src/config-builder.js, segment-viz.js).

The config builder emits partial configs; every shape it can emit must survive
``_validate_config`` untouched and silently. The JS logic itself is checked with
node when it is available.
"""

import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from whispy.core.config import CONFIG_SCHEMA, DEFAULT_CONFIG, _validate_config

DOCS_SRC = Path(__file__).resolve().parent.parent / "docs" / "src"

BUILDER_CONFIGS = [
    {"trigger_mode": "toggle"},
    {"pause_ms": 800, "max_chunk_s": 10},
    {"vad_aggressiveness": 3, "copy_to_clipboard": False},
    {"trigger": "cmd+shift+space"},
    {"trigger": 63},
    {"custom_vocabulary": ["Whispy", "Parakeet"]},
    {"min_chunk_s": 1.0, "max_chunk_s": 1.5},
]


@pytest.mark.parametrize("partial", BUILDER_CONFIGS, ids=lambda c: ",".join(c))
def test_builder_output_survives_validation(partial, capsys):
    validated = _validate_config({**DEFAULT_CONFIG, **partial})
    for key, value in partial.items():
        assert validated[key] == value
    assert capsys.readouterr().err == ""


NODE_SCRIPT = r"""
const assert = require("assert");
const schema = JSON.parse(process.argv[1]);
const dir = process.argv[2];
const b = require(dir + "/config-builder.js");
const v = require(dir + "/segment-viz.js");

const defaults = {};
Object.keys(schema).forEach((k) => { defaults[k] = schema[k].default; });

assert.ok(b.validate("vad_aggressiveness", 5, defaults, schema));
assert.ok(b.validate("vad_aggressiveness", 2.5, defaults, schema));
assert.equal(b.validate("vad_aggressiveness", 3, defaults, schema), null);
assert.ok(b.validate("pause_ms", true, defaults, schema));
assert.ok(b.validate("pause_ms", 0, defaults, schema));
assert.ok(b.validate("min_speech_s", false, defaults, schema));
assert.ok(b.validate("max_chunk_s", 0.4, defaults, schema));
assert.ok(b.validate("max_chunk_s", 0.3, defaults, schema));
assert.equal(b.validate("max_chunk_s", 0.5, defaults, schema), null);
assert.ok(b.validate("trigger", -1, defaults, schema));
assert.equal(b.validate("trigger", null, defaults, schema), null);
assert.ok(b.validate("trigger_mode", "other", defaults, schema));

assert.deepStrictEqual(b.diffFromDefaults(defaults, schema), {});
assert.deepStrictEqual(
  b.diffFromDefaults({ ...defaults, trigger_mode: "toggle" }, schema),
  { trigger_mode: "toggle" }
);
assert.deepStrictEqual(
  b.diffFromDefaults({ ...defaults, custom_vocabulary: [] }, schema), {}
);
assert.deepStrictEqual(b.parseRaw(schema.trigger, " 63 "), 63);
assert.deepStrictEqual(b.parseRaw(schema.trigger, ""), null);

const consts = { hard_max_factor: 1.5, frame_ms: 30, sentence_break_ms: null };
const params = {
  pause_ms: schema.pause_ms.default, min_speech_s: schema.min_speech_s.default,
  soft_gap_ms: schema.soft_gap_ms.default, min_chunk_s: schema.min_chunk_s.default,
  max_chunk_s: schema.max_chunk_s.default,
};
const res = v.segment(v.SAMPLE_TIMELINE, params, consts);
const rules = res.cuts.map((c) => c.rule);
assert.ok(rules.includes("pause"), "pause cut");
assert.ok(rules.includes("soft"), "soft cut");
assert.ok(rules.includes("hard"), "hard cut");
assert.ok(res.cuts.some((c) => c.rule === "pause" && c.reason === "sentence"));
// The short isolated word (400 ms) is never cut on its own: every chunk holds >= min_speech_s
// of voice except possibly the final tail.
res.chunks.slice(0, -1).forEach((c) => assert.ok(c.voiced_s >= params.min_speech_s));
// The first 700 ms pause yields a cut that disappears at pause_ms 800.
const first = res.cuts[0];
assert.equal(first.rule, "pause");
const slow = v.segment(v.SAMPLE_TIMELINE, { ...params, pause_ms: 800 }, consts);
assert.ok(!slow.cuts.some((c) => Math.abs(c.t - first.t) < 0.3 && c.rule === "pause"));
// Raising min_chunk_s flags short chunks as discarded.
const strict = v.segment(v.SAMPLE_TIMELINE, { ...params, min_chunk_s: 3.0 }, consts);
assert.ok(strict.chunks.some((c) => c.discarded));
assert.ok(!res.chunks.some((c) => c.discarded));
console.log("ok");
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_widget_logic_in_node():
    schema = {key: dataclasses.asdict(spec) for key, spec in CONFIG_SCHEMA.items()}
    result = subprocess.run(
        ["node", "-e", NODE_SCRIPT, json.dumps(schema), str(DOCS_SRC)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"

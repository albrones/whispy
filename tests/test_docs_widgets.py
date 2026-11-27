"""Guards for the docs config builder (docs/src/config-builder.js).

The builder emits partial configs; every value it accepts must be one Whispy
reads without falling back (v2/whispy2/src/settings.rs). Its logic is checked
with node when it is available.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DOCS_SRC = Path(__file__).resolve().parent.parent / "docs" / "src"
SCHEMA = json.loads((DOCS_SRC / "config-schema.json").read_text(encoding="utf-8"))

NODE_SCRIPT = r"""
const assert = require("assert");
const schema = JSON.parse(process.argv[1]);
const b = require(process.argv[2] + "/config-builder.js");

const defaults = {};
Object.keys(schema).forEach((k) => { defaults[k] = schema[k].default; });

// Every default is valid, and the diff of the defaults is empty.
Object.keys(schema).forEach((k) => assert.equal(b.validate(k, defaults[k], defaults, schema), null, k));
assert.deepStrictEqual(b.diffFromDefaults(defaults, schema), {});

assert.equal(b.validate("trigger_mode", "toggle", defaults, schema), null);
assert.ok(b.validate("trigger_mode", "other", defaults, schema));
assert.ok(b.validate("copy_to_clipboard", "yes", defaults, schema));
assert.equal(b.validate("omarchy_trigger", "f9_hold", defaults, schema), null);
assert.ok(b.validate("omarchy_trigger", "f13_hold", defaults, schema));

// The trigger is null (Fn) or a keycode: settings.rs refuses a key combination.
assert.equal(b.validate("trigger", null, defaults, schema), null);
assert.equal(b.validate("trigger", 61, defaults, schema), null);
assert.ok(b.validate("trigger", -1, defaults, schema));
assert.ok(b.validate("trigger", "cmd+shift+space", defaults, schema));
assert.deepStrictEqual(b.parseRaw(schema.trigger, " 61 "), 61);
assert.deepStrictEqual(b.parseRaw(schema.trigger, ""), null);

assert.deepStrictEqual(
  b.diffFromDefaults({ ...defaults, trigger_mode: "toggle" }, schema),
  { trigger_mode: "toggle" }
);
console.log("ok");
"""


def test_every_choice_default_is_one_of_its_choices():
    for key, spec in SCHEMA.items():
        if spec["kind"] == "choice":
            assert spec["default"] in spec["choices"], key


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_widget_logic_in_node():
    result = subprocess.run(
        ["node", "-e", NODE_SCRIPT, json.dumps(SCHEMA), str(DOCS_SRC)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"

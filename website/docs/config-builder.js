/* Config builder for the Whispy docs. No dependencies, works from file://.
 * Mirrors the validation of _validate_config in src/whispy/core/config.py: keep them in sync.
 * Pure logic (validate, diffFromDefaults, parseRaw) is exported for node; DOM code only runs in a
 * browser when #config-builder exists. */
"use strict";

function isNumber(v) {
  return typeof v === "number" && Number.isFinite(v);
}

/* Return an error message for `value` of `key`, or null when valid.
 * `values` holds the current values of all keys (used by gt_key). */
function validate(key, value, values, schema) {
  const spec = schema[key];
  if (!spec) return "Unknown setting.";
  switch (spec.kind) {
    case "bool":
      return typeof value === "boolean" ? null : "Must be true or false.";
    case "choice":
      return (spec.choices || []).indexOf(value) >= 0 ? null : "Pick one of: " + (spec.choices || []).join(", ") + ".";
    case "trigger":
      if (value === null) return null;
      if (typeof value === "number") return Number.isInteger(value) && value >= 0 ? null : "A keycode must be a whole number, 0 or more.";
      if (typeof value === "string") return value.trim() !== "" ? null : "Leave empty for the platform default.";
      return "Enter a key name, a keycode, or leave empty.";
    case "str_list":
      if (!Array.isArray(value)) return "Must be a list.";
      return value.every((t) => typeof t === "string" && t.trim() !== "" && t === t.trim()) ? null : "Terms must be non-empty text.";
    case "int":
    case "number": {
      if (!isNumber(value)) return "Enter a number.";
      if (spec.kind === "int" && !Number.isInteger(value)) return "Must be a whole number.";
      if (spec.ge != null && value < spec.ge) return "Must be at least " + spec.ge + ".";
      if (spec.gt != null && value <= spec.gt) return "Must be greater than " + spec.gt + ".";
      if (spec.le != null && value > spec.le) return "Must be at most " + spec.le + ".";
      if (spec.gt_key != null && !(value > values[spec.gt_key])) {
        return "Must be greater than " + spec.gt_key + " (" + values[spec.gt_key] + ").";
      }
      return null;
    }
    default:
      return "Unsupported setting.";
  }
}

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/* Keys whose value differs from the default, in schema order. */
function diffFromDefaults(values, schema) {
  const out = {};
  Object.keys(schema).forEach((key) => {
    if (key in values && !deepEqual(values[key], schema[key].default)) out[key] = values[key];
  });
  return out;
}

/* Turn the text of an input into a typed value (undefined when it cannot be parsed). */
function parseRaw(spec, raw) {
  switch (spec.kind) {
    case "trigger": {
      const t = String(raw).trim();
      if (t === "") return null;
      return /^\d+$/.test(t) ? parseInt(t, 10) : t;
    }
    case "str_list":
      return String(raw).split(/[\n,]/).map((s) => s.trim()).filter((s) => s !== "");
    case "int":
    case "number": {
      const t = String(raw).trim();
      return t === "" ? undefined : Number(t);
    }
    default:
      return raw;
  }
}

/* Display text of a typed value, as shown in a text-like input. */
function formatValue(spec, value) {
  if (spec.kind === "trigger") return value === null ? "" : String(value);
  if (spec.kind === "str_list") return value.join("\n");
  return String(value);
}

/* ---------------------------------------------------------------- DOM */
function initConfigBuilder() {
  const root = document.getElementById("config-builder");
  if (!root) return;
  let schema;
  try {
    schema = JSON.parse(document.getElementById("config-schema").textContent);
  } catch (e) {
    root.textContent = "The configuration schema could not be loaded.";
    return;
  }
  const keys = Object.keys(schema);

  function h(tag, attrs, kids) {
    const e = document.createElement(tag);
    Object.keys(attrs || {}).forEach((k) => {
      if (k === "text") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach((c) => e.appendChild(c));
    return e;
  }

  const lastValid = {};
  keys.forEach((k) => { lastValid[k] = JSON.parse(JSON.stringify(schema[k].default)); });
  const current = {}; // key -> typed value, or undefined when invalid
  const rows = {};

  const form = h("div", { class: "cb-form" });
  const groups = [];
  keys.forEach((key) => {
    const spec = schema[key];
    let g = groups.find((x) => x.name === spec.group);
    if (!g) {
      const fs = h("fieldset", { class: "cb-group" }, [h("legend", { text: spec.group || "Other" })]);
      g = { name: spec.group, el: fs };
      groups.push(g);
      form.appendChild(fs);
    }
    const id = "cb-" + key;
    const helpId = id + "-help", errId = id + "-err";
    const row = h("div", { class: "cb-row" });
    let control;
    if (spec.kind === "bool") {
      control = h("input", { type: "checkbox", id });
      control.checked = !!spec.default;
    } else if (spec.kind === "choice") {
      control = h("select", { id }, (spec.choices || []).map((c) => h("option", { value: c, text: c })));
      control.value = spec.default;
    } else if (spec.kind === "int" || spec.kind === "number") {
      control = h("input", { type: "number", id, inputmode: "decimal" });
      const step = spec.step != null ? spec.step : (spec.kind === "int" ? 1 : "any");
      control.setAttribute("step", step);
      if (spec.ge != null) control.setAttribute("min", spec.ge);
      else if (spec.gt != null) control.setAttribute("min", spec.gt + (typeof step === "number" ? step : 0));
      if (spec.le != null) control.setAttribute("max", spec.le);
      control.value = formatValue(spec, spec.default);
    } else if (spec.kind === "trigger") {
      control = h("input", { type: "text", id, placeholder: "platform default (Fn / Right Ctrl)", autocomplete: "off", spellcheck: "false" });
    } else {
      control = h("textarea", { id, rows: "3", placeholder: "one term per line", spellcheck: "false" });
      control.value = formatValue(spec, spec.default);
    }
    control.setAttribute("aria-describedby", helpId + " " + errId);

    const label = h("label", { for: id, class: "cb-label" }, [h("code", { text: key })]);
    if (spec.unit) label.appendChild(h("span", { class: "cb-unit", text: " (" + spec.unit + ")" }));
    const reset = h("button", { type: "button", class: "cb-reset", text: "Reset" });
    reset.hidden = true;
    reset.setAttribute("aria-label", "Reset " + key + " to default");
    const head = h("div", { class: "cb-head" }, [label, reset]);
    const help = h("p", { class: "cb-help", id: helpId, text: spec.description });
    const err = h("p", { class: "cb-error", id: errId });
    err.hidden = true;
    row.append(head, control, help, err);
    g.el.appendChild(row);
    rows[key] = { spec, control, reset, err };

    control.addEventListener(spec.kind === "bool" || spec.kind === "choice" ? "change" : "input", () => update(key));
    reset.addEventListener("click", () => {
      writeControl(key, spec.default);
      update(key);
      control.focus();
    });
  });

  function writeControl(key, value) {
    const { spec, control } = rows[key];
    if (spec.kind === "bool") control.checked = !!value;
    else control.value = formatValue(spec, value);
  }
  function readControl(key) {
    const { spec, control } = rows[key];
    return spec.kind === "bool" ? control.checked : parseRaw(spec, control.value);
  }

  const pre = h("pre", { class: "cb-pre" });
  const code = h("code", { id: "cb-output" });
  pre.appendChild(code);
  const copy = h("button", { type: "button", class: "cb-copy", text: "Copy" });
  const status = h("span", { class: "cb-status", role: "status", "aria-live": "polite" });
  const note = h("p", { class: "cb-note", text: "Merge these keys into ~/.config/whispy/config.json (create it if missing), then restart Whispy. Keys you leave out keep their current value." });
  const outHead = h("div", { class: "cb-out-head" }, [h("h3", { text: "Your config" }), copy, status]);
  const out = h("div", { class: "cb-out" }, [outHead, pre, note]);
  root.append(form, out);

  let copyTimer = 0;
  copy.addEventListener("click", () => {
    const text = code.textContent;
    const done = () => {
      status.textContent = "Copied";
      copy.textContent = "Copied";
      clearTimeout(copyTimer);
      copyTimer = setTimeout(() => { status.textContent = ""; copy.textContent = "Copy"; }, 1500);
    };
    const fallback = () => {
      const ta = h("textarea", { "aria-hidden": "true", tabindex: "-1", style: "position:fixed;left:-9999px;top:0" });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { status.textContent = "Press Ctrl/Cmd+C to copy."; }
      document.body.removeChild(ta);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  });

  function recompute(changedKey) {
    keys.forEach((key) => {
      const raw = readControl(key);
      // Cross-checks use the other key's typed value when valid, else its last valid value.
      current[key] = raw;
    });
    const effective = {};
    keys.forEach((k) => { effective[k] = lastValid[k]; });
    // Validate in schema order so a gt_key sees its dependency's freshly validated value.
    keys.forEach((key) => {
      const spec = schema[key];
      const value = current[key];
      const msg = value === undefined ? "Enter a number." : validate(key, value, effective, schema);
      const r = rows[key];
      if (msg) {
        r.control.setAttribute("aria-invalid", "true");
        r.err.textContent = msg;
        r.err.hidden = false;
        current[key] = undefined;
      } else {
        r.control.removeAttribute("aria-invalid");
        r.err.textContent = "";
        r.err.hidden = true;
        lastValid[key] = value;
        effective[key] = value;
      }
      r.reset.hidden = deepEqual(readControl(key), spec.default);
    });
    return effective;
  }

  function update(changedKey) {
    const effective = recompute(changedKey);
    const emitted = {};
    keys.forEach((k) => { if (current[k] !== undefined) emitted[k] = current[k]; });
    code.textContent = JSON.stringify(diffFromDefaults(emitted, schema), null, 2);
    document.dispatchEvent(new CustomEvent("whispy:config-change", { detail: { values: Object.assign({}, effective) } }));
  }

  recompute(null);
  code.textContent = "{}";
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initConfigBuilder);
  else initConfigBuilder();
}
if (typeof module !== "undefined") module.exports = { validate, diffFromDefaults, parseRaw, formatValue, deepEqual };

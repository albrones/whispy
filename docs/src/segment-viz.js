/* Simplified illustration of src/whispy/core/segmentation.py (Segmenter.feed). Keep the rule order in sync.
 *
 * Streaming segmentation visualizer for the Whispy docs. No dependencies.
 * Pure logic (segment, SAMPLE_TIMELINE) is exported for node; DOM code only runs in a browser
 * when #segment-viz exists.
 */
"use strict";

// Mirrors LONE_WORD_PAUSE_S in segmentation.py: past this much silence a short chunk is emitted anyway.
const LONE_WORD_PAUSE_MS = 2000;

// [kind, ms] segments, ~27 s. At the default parameters (pause 600, min speech 0.7, soft gap 350,
// max chunk 8.0, hard factor 1.5) this produces:
//   1. a pause (SENTENCE) cut after a 700 ms pause,
//   2. a 400 ms word + 700 ms pause that is NOT cut (min_speech_s), then a phrase and a second pause cut,
//   3. a run-on stretch with 360 ms gaps that is cut softly once past 8 s,
//   4. a stretch whose gaps are all < 350 ms and hits the 12 s hard cap.
const SAMPLE_TIMELINE = [
  ["speech", 2000], ["silence", 700],
  ["speech", 400], ["silence", 700],
  ["speech", 1500], ["silence", 700],
  ["speech", 2800], ["silence", 360],
  ["speech", 2800], ["silence", 360],
  ["speech", 1800], ["silence", 360],
  ["speech", 3000], ["silence", 300],
  ["speech", 3400], ["silence", 300],
  ["speech", 3400], ["silence", 300],
  ["speech", 1900], ["silence", 300],
  ["speech", 1000], ["silence", 700],
];

/* Walk the timeline frame by frame, in the same rule order as Segmenter.feed:
 *   1. a pause closes the chunk (silence >= pause_ms and voiced >= min_speech_s, or silence >= 2 s);
 *   2. else once buffered >= max_chunk_s and silence >= soft_gap_ms: soft cut;
 *   3. else unconditionally at max_chunk_s * hard_max_factor: hard cut.
 * Simplification: frames are exact (no VAD noise), and the leftover audio at the end is flushed as
 * a final chunk (flush_tail). A chunk shorter than min_chunk_s is flagged discarded. */
function segment(timeline, params, constants) {
  const frameMs = constants.frame_ms || 30;
  const hardFactor = constants.hard_max_factor || 1.5;
  const pauseMs = params.pause_ms;
  const sentenceMs = constants.sentence_break_ms == null ? pauseMs : constants.sentence_break_ms;
  const minSpeechMs = params.min_speech_s * 1000;
  const softMs = params.soft_gap_ms;
  const maxMs = params.max_chunk_s * 1000;
  const minChunkMs = params.min_chunk_s * 1000;
  const eps = 1e-6;

  const cuts = [];
  const chunks = [];
  let chunkStart = 0, buffered = 0, speech = 0, silence = 0, have = false;
  let now = 0;

  function close(reason, rule) {
    cuts.push({ t: now / 1000, reason, rule });
    chunks.push({
      start: chunkStart / 1000, end: now / 1000, voiced_s: speech / 1000,
      discarded: (now - chunkStart) < minChunkMs - eps, rule,
    });
    chunkStart = now; buffered = 0; speech = 0; silence = 0; have = false;
  }

  for (const [kind, ms] of timeline) {
    const n = Math.round(ms / frameMs);
    for (let i = 0; i < n; i++) {
      now += frameMs;
      buffered += frameMs;
      if (kind === "speech") { have = true; speech += frameMs; silence = 0; } else { silence += frameMs; }
      if (!have) continue;
      const pauseCloses = silence >= pauseMs - eps &&
        (speech >= minSpeechMs - eps || silence >= LONE_WORD_PAUSE_MS - eps);
      if (pauseCloses) {
        close(silence >= sentenceMs - eps ? "sentence" : "continuation", "pause");
      } else if (buffered >= maxMs * hardFactor - eps) {
        close("continuation", "hard");
      } else if (buffered >= maxMs - eps && silence >= softMs - eps) {
        close("continuation", "soft");
      }
    }
  }
  if (have) { // flush_tail
    chunks.push({
      start: chunkStart / 1000, end: now / 1000, voiced_s: speech / 1000,
      discarded: (now - chunkStart) < minChunkMs - eps, rule: "end",
    });
  }
  return { cuts, chunks, duration: now / 1000 };
}

function summarize(result) {
  const c = { pause: 0, soft: 0, hard: 0 };
  result.cuts.forEach((k) => { c[k.rule] += 1; });
  const parts = ["pause", "soft", "hard"].filter((r) => c[r]).map((r) => c[r] + " " + r + " cut" + (c[r] > 1 ? "s" : ""));
  const n = result.chunks.length;
  return n + " chunk" + (n === 1 ? "" : "s") + (parts.length ? ": " + parts.join(", ") : "");
}

/* ---------------------------------------------------------------- DOM */
function initSegmentViz() {
  const root = document.getElementById("segment-viz");
  if (!root) return;
  const SVGNS = "http://www.w3.org/2000/svg";
  const W = 640, H = 190, X0 = 12, X1 = 628;

  let schema = {}, constants = { hard_max_factor: 1.5, frame_ms: 30, sentence_break_ms: null };
  try { schema = JSON.parse(document.getElementById("config-schema").textContent); } catch (e) { /* defaults below */ }
  try { constants = JSON.parse(document.getElementById("segmenter-constants").textContent); } catch (e) { /* defaults */ }
  const fallback = { pause_ms: 600, min_speech_s: 0.7, soft_gap_ms: 350, min_chunk_s: 0.4, max_chunk_s: 8.0 };
  const params = {};
  Object.keys(fallback).forEach((k) => { params[k] = schema[k] && typeof schema[k].default === "number" ? schema[k].default : fallback[k]; });

  const reduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };

  function el(name, attrs, text) {
    const e = document.createElementNS(SVGNS, name);
    Object.keys(attrs || {}).forEach((k) => e.setAttribute(k, attrs[k]));
    if (text != null) e.textContent = text;
    return e;
  }
  function html(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  const fig = html("figure", "wv-fig");
  const svgHost = html("div", "wv-svg-host");
  const list = html("ul", "wv-visually-hidden");
  const legend = html("ul", "wv-legend");
  [["wv-sw wv-sw-speech", "Speech"], ["wv-sw wv-sw-a", "Chunk"], ["wv-sw wv-sw-b", "Next chunk"],
   ["wv-sw wv-sw-discarded", "Discarded (shorter than min chunk)"], ["wv-sw wv-sw-cut", "Cut: pause / soft / hard"]]
    .forEach(([c, t]) => { const li = html("li"); li.appendChild(html("span", c)); li.appendChild(document.createTextNode(" " + t)); legend.appendChild(li); });
  const cap = html("figcaption", "wv-caption",
    "Simplified illustration of how Whispy cuts a recording into chunks — not a recording of the real segmenter.");
  fig.append(svgHost, legend, cap, list);
  root.appendChild(fig);

  let playhead = null, total = 1, rafId = 0, t0 = 0;

  function render() {
    const res = segment(SAMPLE_TIMELINE, params, constants);
    total = res.duration;
    const sx = (s) => X0 + (s / total) * (X1 - X0);
    const svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": summarize(res), class: "wv-svg", preserveAspectRatio: "xMidYMid meet" });

    res.chunks.forEach((c, i) => {
      const cls = c.discarded ? "wv-chunk wv-chunk-discarded" : "wv-chunk " + (i % 2 ? "wv-chunk-b" : "wv-chunk-a");
      svg.appendChild(el("rect", { class: cls, x: sx(c.start), y: 26, width: Math.max(1, sx(c.end) - sx(c.start)), height: 78, rx: 3 }));
      svg.appendChild(el("text", { class: "wv-label", x: (sx(c.start) + sx(c.end)) / 2, y: 20, "text-anchor": "middle" }, String(i + 1)));
    });

    let tt = 0;
    SAMPLE_TIMELINE.forEach(([kind, ms]) => {
      if (kind === "speech") {
        svg.appendChild(el("rect", { class: "wv-speech", x: sx(tt / 1000), y: 46, width: Math.max(1, sx((tt + ms) / 1000) - sx(tt / 1000)), height: 38, rx: 2 }));
      }
      tt += ms;
    });
    svg.appendChild(el("line", { class: "wv-base", x1: X0, x2: X1, y1: 65, y2: 65 }));

    const rowEnd = [-Infinity, -Infinity]; // right edge of the last label placed on each row
    res.cuts.forEach((k) => {
      const x = sx(k.t);
      svg.appendChild(el("line", { class: "wv-cut wv-cut-" + k.rule, x1: x, x2: x, y1: 24, y2: 112 }));
      const half = (k.rule.length * 7.5 + 4) / 2; // rough label half-width at 13px
      const cx = Math.min(W - 2 - half, Math.max(2 + half, x)); // never clipped by the viewBox
      const row = cx - half >= rowEnd[0] + 4 ? 0 : 1;
      rowEnd[row] = cx + half;
      svg.appendChild(el("text", { class: "wv-label wv-label-cut", x: cx, y: 126 + row * 15, "text-anchor": "middle" }, k.rule));
    });

    svg.appendChild(el("line", { class: "wv-axis", x1: X0, x2: X1, y1: 156, y2: 156 }));
    const step = total > 40 ? 10 : 5;
    for (let s = 0; s <= total + 1e-6; s += step) {
      svg.appendChild(el("line", { class: "wv-axis", x1: sx(s), x2: sx(s), y1: 156, y2: 162 }));
      svg.appendChild(el("text", { class: "wv-label", x: sx(s), y: 178, "text-anchor": s === 0 ? "start" : "middle" }, s + " s"));
    }
    playhead = el("line", { class: "wv-playhead", x1: X0, x2: X0, y1: 22, y2: 156 });
    if (reduce.matches) playhead.setAttribute("display", "none");
    svg.appendChild(playhead);

    svgHost.replaceChildren(svg);
    list.replaceChildren();
    if (!res.cuts.length) list.appendChild(html("li", null, "No cuts: the whole recording is one chunk."));
    res.cuts.forEach((k) => {
      list.appendChild(html("li", null, "At " + k.t.toFixed(2) + " s: " + k.rule + " cut (" + k.reason + ")."));
    });
    res.chunks.forEach((c, i) => {
      if (c.discarded) list.appendChild(html("li", null, "Chunk " + (i + 1) + " is discarded: shorter than the minimum chunk length."));
    });
  }

  function frame(now) {
    rafId = 0;
    if (reduce.matches || !playhead) return;
    if (!t0) t0 = now;
    const s = ((now - t0) / 1000) % total;
    const x = X0 + (s / total) * (X1 - X0);
    playhead.setAttribute("x1", x);
    playhead.setAttribute("x2", x);
    rafId = requestAnimationFrame(frame);
  }
  function start() {
    if (rafId || reduce.matches || typeof requestAnimationFrame !== "function") return;
    t0 = 0;
    rafId = requestAnimationFrame(frame);
  }
  if (reduce.addEventListener) {
    reduce.addEventListener("change", () => { render(); if (reduce.matches) { if (rafId) cancelAnimationFrame(rafId); rafId = 0; } else start(); });
  }

  document.addEventListener("whispy:config-change", (ev) => {
    const v = ev.detail && ev.detail.values;
    if (!v) return;
    Object.keys(params).forEach((k) => { if (typeof v[k] === "number" && isFinite(v[k])) params[k] = v[k]; });
    render();
  });

  render();
  start();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initSegmentViz);
  else initSegmentViz();
}
if (typeof module !== "undefined") module.exports = { segment, summarize, SAMPLE_TIMELINE };

/* Whispy docs: OS switcher, copy buttons, install checklist. No dependencies. */
(function () {
  "use strict";

  var OS_KEY = "whispy-docs-os";
  var STEPS_KEY = "whispy-docs-steps";

  function store(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ }
  }
  function load(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  // --- OS switcher ---
  function setOs(os, persist) {
    document.documentElement.dataset.os = os;
    document.querySelectorAll("[data-set-os]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.dataset.setOs === os));
    });
    if (persist) store(OS_KEY, os);
  }
  document.querySelectorAll("[data-set-os]").forEach(function (btn) {
    btn.addEventListener("click", function () { setOs(btn.dataset.setOs, true); });
  });
  setOs(document.documentElement.dataset.os === "linux" ? "linux" : "macos", false);

  // --- Copy buttons ---
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy") ? resolve() : reject(new Error("copy failed"));
      } catch (e) {
        reject(e);
      } finally {
        document.body.removeChild(area);
      }
    });
  }

  function flash(btn) {
    var label = btn.dataset.label || btn.textContent;
    btn.dataset.label = label;
    btn.textContent = "Copied";
    clearTimeout(btn._t);
    btn._t = setTimeout(function () { btn.textContent = label; }, 1600);
  }

  function wireCopy(btn, getText) {
    btn.hidden = false;
    btn.addEventListener("click", function () {
      copyText(getText()).then(function () { flash(btn); }, function () { /* leave text selectable */ });
    });
  }

  document.querySelectorAll("pre[data-copy]").forEach(function (pre) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.setAttribute("aria-label", "Copy command");
    var wrap = document.createElement("div");
    wrap.className = "copy-wrap";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    wrap.appendChild(btn);
    wireCopy(btn, function () { return pre.textContent.replace(/\n$/, ""); });
  });

  document.querySelectorAll("button[data-copy-target]").forEach(function (btn) {
    wireCopy(btn, function () {
      var target = document.getElementById(btn.dataset.copyTarget);
      return target ? target.textContent.trim() : "";
    });
  });

  // --- Install checklist ---
  var done = {};
  try { done = JSON.parse(load(STEPS_KEY) || "{}") || {}; } catch (e) { done = {}; }
  document.querySelectorAll("input[type=checkbox][data-step]").forEach(function (box) {
    box.checked = !!done[box.dataset.step];
    box.addEventListener("change", function () {
      if (box.checked) done[box.dataset.step] = true; else delete done[box.dataset.step];
      store(STEPS_KEY, JSON.stringify(done));
    });
  });
})();

// Braille waveform animation — mirrors the macOS menu bar icon.
// Frames are the "waverows" set, vendored from unicode-animations (MIT,
// github.com/gunnargray-dev/unicode-animations) and kept in sync with the app's
// src/whispy/ui/unicode_anim.py. A sine wave scrolls left->right across 4
// braille characters; it reads like an audio waveform.
(function () {
  "use strict";

  const WAVEROWS = [
    "⠖⠉⠉⠑", "⡠⠖⠉⠉", "⣠⡠⠖⠉", "⣄⣠⡠⠖",
    "⠢⣄⣠⡠", "⠙⠢⣄⣠", "⠉⠙⠢⣄", "⠊⠉⠙⠢",
    "⠜⠊⠉⠙", "⡤⠜⠊⠉", "⣀⡤⠜⠊", "⢤⣀⡤⠜",
    "⠣⢤⣀⡤", "⠑⠣⢤⣀", "⠉⠑⠣⢤", "⠋⠉⠑⠣",
  ];
  const IDLE_FRAME = "⣀⣤⣶⣤";
  const INTERVAL = 90; // ms — matches the app's WAVEROWS_INTERVAL

  const targets = Array.from(document.querySelectorAll("[data-braille-wave]"));
  if (!targets.length) return;

  const reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (reduceMotion) {
    targets.forEach((el) => (el.textContent = IDLE_FRAME));
    return;
  }

  let frame = 0;
  setInterval(() => {
    const glyph = WAVEROWS[frame % WAVEROWS.length];
    targets.forEach((el) => (el.textContent = glyph));
    frame++;
  }, INTERVAL);
})();

// Copy-to-clipboard for the install command blocks.
(function () {
  "use strict";

  document.querySelectorAll(".btn-copy").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (!target || !navigator.clipboard) return;
      try {
        await navigator.clipboard.writeText(target.textContent.trim());
        const original = btn.textContent;
        btn.textContent = "Copied";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = original;
          btn.classList.remove("copied");
        }, 1600);
      } catch (err) {
        /* clipboard unavailable — silently ignore */
      }
    });
  });
})();

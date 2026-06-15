// Animated hero waveform — echoes the in-app recording visualization.
// Brand green (#24bf9e) bars that gently react to a synthetic "voice" signal.
// Disabled entirely when the user prefers reduced motion.
(function () {
  "use strict";

  const canvas = document.getElementById("waveform");
  if (!canvas || !canvas.getContext) return;

  const ctx = canvas.getContext("2d");
  const reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Crisp rendering on retina displays.
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || canvas.width;
  const cssH = canvas.clientHeight || canvas.height;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  ctx.scale(dpr, dpr);

  const BARS = 28;
  const GREEN = "#24bf9e";
  const gap = 4;
  const barW = (cssW - gap * (BARS - 1)) / BARS;
  const levels = new Array(BARS).fill(0.15);

  function drawFrame(getTarget) {
    ctx.clearRect(0, 0, cssW, cssH);
    for (let i = 0; i < BARS; i++) {
      const target = getTarget(i);
      // ease toward the target for a fluid feel
      levels[i] += (target - levels[i]) * 0.25;
      const h = Math.max(2, levels[i] * cssH);
      const x = i * (barW + gap);
      const y = (cssH - h) / 2;
      ctx.fillStyle = GREEN;
      ctx.globalAlpha = 0.55 + levels[i] * 0.45;
      const r = Math.min(barW / 2, 3);
      roundRect(ctx, x, y, barW, h, r);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function roundRect(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }

  if (reduceMotion) {
    // Static, calm waveform — no animation loop.
    drawFrame((i) => {
      const center = (BARS - 1) / 2;
      const d = Math.abs(i - center) / center;
      return 0.25 + (1 - d) * 0.4;
    });
    return;
  }

  let t = 0;
  function animate() {
    t += 0.08;
    drawFrame((i) => {
      const center = (BARS - 1) / 2;
      const envelope = 1 - Math.abs(i - center) / center; // taller in the middle
      const wobble =
        0.5 +
        0.5 * Math.sin(t + i * 0.5) * Math.sin(t * 0.6 + i * 0.21);
      return 0.12 + envelope * (0.25 + 0.6 * Math.abs(wobble));
    });
    requestAnimationFrame(animate);
  }
  animate();
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

// Braille waveform + interactive workflow demo for the Whispy site.
//
// The WAVEROWS frames are vendored from unicode-animations (MIT,
// github.com/gunnargray-dev/unicode-animations) and kept in sync with the app's
// src/whispy/ui/unicode_anim.py. A sine wave scrolls left->right across 4
// braille characters; it reads like an audio waveform. IDLE_FRAME is the calm
// glyph the real menu bar rests on when Whispy is not listening.

"use strict";

const WAVEROWS = [
  "⠖⠉⠉⠑", "⡠⠖⠉⠉", "⣠⡠⠖⠉", "⣄⣠⡠⠖",
  "⠢⣄⣠⡠", "⠙⠢⣄⣠", "⠉⠙⠢⣄", "⠊⠉⠙⠢",
  "⠜⠊⠉⠙", "⡤⠜⠊⠉", "⣀⡤⠜⠊", "⢤⣀⡤⠜",
  "⠣⢤⣀⡤", "⠑⠣⢤⣀", "⠉⠑⠣⢤", "⠋⠉⠑⠣",
];
const IDLE_FRAME = "⣀⣤⣶⣤";
const INTERVAL = 90; // ms — matches the app's WAVEROWS_INTERVAL

const REDUCE_MOTION =
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Scrolls the braille wave across an element; rests on IDLE_FRAME when stopped.
// Mirrors the menu bar app: it animates only while Whispy is "active".
class BrailleAnimator {
  constructor(el) {
    this.el = el;
    this.frame = 0;
    this.timer = null;
    this.el.textContent = IDLE_FRAME;
  }
  get running() {
    return this.timer !== null;
  }
  start() {
    if (this.timer) return;
    this.timer = setInterval(() => {
      this.el.textContent = WAVEROWS[this.frame % WAVEROWS.length];
      this.frame += 1;
    }, INTERVAL);
  }
  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.frame = 0;
    this.el.textContent = IDLE_FRAME;
  }
}

// Audio-reactive bar pill — a faithful port of the app's WaveformView math
// (src/whispy/ui/waveform_window.py): symmetric envelope, per-bar sine wobble,
// bars driven by a smoothed level. Here the "level" is a synthesized speech
// envelope since there's no real microphone on the page.
class WaveformPill {
  constructor(el) {
    this.el = el;
    this.bars = Array.from(el.querySelectorAll("span"));
    this.n = this.bars.length;
    this.mid = (this.n - 1) / 2;
    this.raf = null;
    this.level = 0;
    this.t = 0;
    this.last = 0;
  }
  start() {
    if (this.raf) return;
    this.el.classList.add("is-on");
    this.last = performance.now();
    const loop = (now) => {
      const dt = Math.min((now - this.last) / 1000, 0.05);
      this.last = now;
      this.t += dt;

      // Synthesized speech loudness: layered sines + a touch of noise.
      const target = Math.min(
        1,
        Math.max(
          0,
          0.5 +
            0.32 * Math.sin(this.t * 3.1) +
            0.18 * Math.sin(this.t * 7.7 + 1) +
            (Math.random() - 0.5) * 0.12
        )
      );
      this.level += (target - this.level) * Math.min(dt * 8, 1);
      const disp = Math.min(Math.pow(this.level, 0.5) * 1.6, 1); // gamma + gain

      for (let i = 0; i < this.n; i++) {
        let env = 1 - Math.abs(i - this.mid) / this.mid;
        env = 0.45 + 0.55 * env; // taller in the middle
        const wobble = 0.5 + 0.5 * Math.sin(this.t * 6 + i * 0.9);
        const amount = disp * env * (0.6 + 0.4 * wobble);
        this.bars[i].style.height = `${(4 + 26 * amount).toFixed(1)}px`;
      }
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }
  stop() {
    this.el.classList.remove("is-on");
    if (this.raf) {
      cancelAnimationFrame(this.raf);
      this.raf = null;
    }
  }
}

// --- Hero menu bar icon: cyclic listen-then-rest, like the real app ----------
(function heroIcon() {
  const el = document.querySelector("[data-braille-wave]");
  if (!el) return;
  if (REDUCE_MOTION) {
    el.textContent = IDLE_FRAME;
    return;
  }
  const anim = new BrailleAnimator(el);
  (async function loop() {
    while (true) {
      anim.start();
      await sleep(2300); // listening
      anim.stop();
      await sleep(1900); // resting on the idle glyph
    }
  })();
})();

// --- Subtle braille drift: a slow tick of dots in a few accent spots ---------
// Deliberately gentle — a slow scroll/shimmer, not the fast recording wave.
(function brailleDrift() {
  if (REDUCE_MOTION) return;

  const SETS = {
    // Slow horizontal wave (reuses the brand frames, trimmed to two cells).
    wave: { frames: WAVEROWS.map((f) => f.slice(0, 2)), interval: 150 },
    // Gentle density shimmer that keeps the glyph bold.
    shimmer: { frames: ["⠿", "⡿", "⣟", "⣿", "⢿", "⡿"], interval: 320 },
  };

  document.querySelectorAll("[data-braille-drift]").forEach((el, idx) => {
    const set = SETS[el.dataset.brailleDrift] || SETS.shimmer;
    let i = idx; // stagger so neighbours aren't in lockstep
    setInterval(() => {
      el.textContent = set.frames[i % set.frames.length];
      i += 1;
    }, set.interval);
  });
})();

// --- Interactive workflow demo ----------------------------------------------
(function workflowDemo() {
  const stage = document.querySelector("[data-demo]");
  if (!stage) return;

  const el = (sel) => stage.querySelector(sel);
  const brailleEl = el("[data-demo-braille]");
  const trigger = el("[data-demo-trigger]");
  const dropdown = el("[data-demo-dropdown]");
  const submenu = el("[data-demo-submenu]");
  const langValue = el("[data-demo-lang]");
  const langRow = el("[data-demo-lang-row]");
  const output = el("[data-demo-output]");
  const editor = el("[data-demo-editor]");
  const caption = el("[data-demo-caption]");
  const fnKey = el("[data-demo-fn]");
  const cursor = el("[data-demo-cursor]");

  const anim = new BrailleAnimator(brailleEl);
  const pill = new WaveformPill(el("[data-demo-pill]"));

  const PHRASES = {
    fr: "Bonjour, bienvenue sur Whispy.",
    en: "Hello, welcome to Whispy.",
  };
  const LANG_LABEL = { fr: "French", en: "English" };
  const SUB_ITEMS = {
    fr: el('[data-demo-sub="fr"]'),
    en: el('[data-demo-sub="en"]'),
  };

  let lang = "fr";

  function setCaption(text, mode) {
    caption.textContent = text;
    caption.dataset.mode = mode || "idle";
  }

  // Move the fake pointer to the center of a target element.
  async function moveCursorTo(target, { settle = 720 } = {}) {
    const s = stage.getBoundingClientRect();
    const t = target.getBoundingClientRect();
    cursor.style.left = `${t.left - s.left + t.width / 2}px`;
    cursor.style.top = `${t.top - s.top + t.height / 2}px`;
    await sleep(settle);
  }

  async function clickPulse() {
    cursor.classList.add("is-click");
    await sleep(180);
    cursor.classList.remove("is-click");
    await sleep(120);
  }

  async function typewriter(text) {
    output.textContent = "";
    editor.classList.add("is-typing");
    for (const ch of text) {
      output.textContent += ch;
      await sleep(ch === " " ? 40 : 38 + Math.floor(Math.random() * 45));
    }
    editor.classList.remove("is-typing");
  }

  // One dictation pass: rest -> listen (icon animates) -> rest -> type.
  async function dictate() {
    const phrase = PHRASES[lang];
    editor.classList.add("is-focused"); // caret blinks in the field
    output.textContent = "";

    setCaption("Hold Fn to dictate", "idle");
    await sleep(900);

    // Press Fn — Whispy starts listening: menu bar icon animates and the
    // on-screen waveform pill fades in, exactly like the real app.
    fnKey.classList.add("is-down");
    anim.start();
    pill.start();
    setCaption("● Listening…", "live");
    await sleep(2400);

    // Release Fn — icon settles back to idle, pill fades out, it transcribes.
    fnKey.classList.remove("is-down");
    anim.stop();
    pill.stop();
    setCaption("Transcribing…", "work");
    await sleep(650);

    // Text lands in the focused field.
    await typewriter(phrase);
    setCaption("Inserted into the active app", "done");
    editor.classList.remove("is-focused");
    await sleep(1500);
  }

  async function openMenu() {
    await moveCursorTo(trigger);
    await clickPulse();
    trigger.classList.add("is-active");
    dropdown.classList.add("is-open");
    setCaption("Menu bar settings", "idle");
    await sleep(700);
  }

  function closeMenu() {
    dropdown.classList.remove("is-open");
    submenu.classList.remove("is-open");
    langRow.classList.remove("is-active");
    trigger.classList.remove("is-active");
  }

  // Open the menu, switch the dictation language, close it.
  async function switchLanguage(to) {
    await openMenu();

    langRow.classList.add("is-active");
    await moveCursorTo(langRow, { settle: 520 });
    submenu.classList.add("is-open");
    await sleep(450);

    await moveCursorTo(SUB_ITEMS[to], { settle: 560 });
    await clickPulse();
    SUB_ITEMS.fr.classList.toggle("is-checked", to === "fr");
    SUB_ITEMS.en.classList.toggle("is-checked", to === "en");
    langValue.textContent = LANG_LABEL[to];
    lang = to;
    setCaption(`Language → ${LANG_LABEL[to]}`, "done");
    await sleep(750);

    closeMenu();
    await sleep(550);
  }

  // Render the calm end-state for users who prefer reduced motion.
  if (REDUCE_MOTION) {
    brailleEl.textContent = IDLE_FRAME;
    output.textContent = PHRASES.fr;
    setCaption("Hold Fn, speak, release", "idle");
    return;
  }

  let started = false;
  async function run() {
    if (started) return;
    started = true;
    while (true) {
      await dictate(); // French
      await switchLanguage("en"); // change language from the menu bar
      await dictate(); // English
      await switchLanguage("fr"); // back to French, loop
    }
  }

  // Only start when the demo scrolls into view (saves CPU, feels intentional).
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          run();
          io.disconnect();
        }
      },
      { threshold: 0.4 }
    );
    io.observe(stage);
  } else {
    run();
  }
})();

// --- Copy-to-clipboard for the install command blocks ------------------------
(function copyButtons() {
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

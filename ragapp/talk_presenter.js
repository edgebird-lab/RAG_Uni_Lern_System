/**
 * Suchbarer Vortrags-Presenter. Zustand nur ueber Klassen/Inline-Styles (seek(t)).
 * window.TalkPresenter.load(cues); TalkPresenter.seek(seconds);
 */
(function () {
  const TITLE_LETTER_S = 0.4;
  const SLIDE_FADE_S = 0.08;
  const KEYWORD_PUNCH_S = 0.35;
  const MERKSATZ_S = 0.35;
  const TITLE_RULE_S = 0.35;
  const FIGURE_FADE_S = 0.45;
  const COUNT_S = 0.7;

  const TalkPresenter = {
    cues: null,
    roots: [],
    prepared: false,

    load(cues) {
      this.cues = cues || { slides: [], events: [] };
      this._prepare();
      this.seek(0);
      return this;
    },

    seek(seconds) {
      if (!this.cues) return this;
      const t = Number(seconds) || 0;
      const state = this._stateAt(t);
      this._apply(state, t);
      return this;
    },

    _sectionsIn(root) {
      if (root.tagName === "SECTION") return root;
      return root.querySelector("section");
    },

    _wrapLetters(heading) {
      if (!heading || heading.dataset.talkWrapped === "1") return;
      const wrapText = (textNode, extra) => {
        const text = textNode.textContent || "";
        const frag = document.createDocumentFragment();
        for (const ch of text) {
          const span = document.createElement("span");
          span.className = extra ? "talk-letter talk-keyword-letter" : "talk-letter";
          span.textContent = ch === " " ? "\u00a0" : ch;
          frag.appendChild(span);
        }
        textNode.parentNode.replaceChild(frag, textNode);
      };
      const walk = (el, extra) => {
        [...el.childNodes].forEach((node) => {
          if (node.nodeType === 3) {
            wrapText(node, extra);
          } else if (node.nodeType === 1) {
            const kw = extra || /^(STRONG|B)$/i.test(node.tagName);
            walk(node, kw);
          }
        });
      };
      walk(heading, false);
      heading.dataset.talkWrapped = "1";
    },

    _wrapCount(heading) {
      if (!heading || heading.dataset.talkCount === "1") return;
      const re = /(\d+(?:[.,]\d+)?)(\s*%|\s*Prozent)?/;
      const walker = document.createTreeWalker(heading, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (const node of nodes) {
        const text = node.textContent || "";
        const m = re.exec(text);
        if (!m) continue;
        const span = document.createElement("span");
        span.className = "talk-count";
        const raw = m[1];
        const sep = raw.indexOf(",") >= 0 ? "," : ".";
        span.dataset.to = raw.replace(",", ".");
        span.dataset.decimals = String(sep && raw.indexOf(sep) >= 0
          ? (raw.split(sep)[1] || "").length
          : 0);
        span.dataset.suffix = m[2] || "";
        span.dataset.sep = sep;
        span.textContent = m[0];
        const after = node.splitText(m.index);
        after.nodeValue = after.nodeValue.slice(m[0].length);
        node.parentNode.insertBefore(span, after);
        heading.dataset.talkCount = "1";
        break;
      }
    },

    _formatCount(to, frac, decimals, suffix, sep) {
      const v = Number(to) * frac;
      let shown;
      if (decimals > 0) shown = v.toFixed(decimals);
      else shown = String(Math.round(v));
      if (sep === ",") shown = shown.replace(".", ",");
      return shown + (suffix || "");
    },

    _frac(t, start, dur) {
      return Math.min(1, Math.max(0, (t - start) / dur));
    },

    _prepare() {
      document.body.classList.add("talk-presenter-on");
      document.body.classList.toggle("talk-youtube", Boolean((this.cues || {}).youtube));
      const svgs = [...document.querySelectorAll("svg.bespoke-marp-slide")];
      this.roots = svgs.length ? svgs : [...document.querySelectorAll("section")];
      this.roots.forEach((root, slideIdx) => {
        const section = this._sectionsIn(root);
        if (!section) return;
        const heading = section.querySelector("h1, h2, marp-h1, marp-h2");
        const isCard = section.classList.contains("card");
        if (heading) {
          heading.classList.add("talk-title");
          if (isCard) heading.classList.add("talk-card-word");
          if (isCard) this._wrapCount(heading);
          if (!heading.querySelector(".talk-count")) this._wrapLetters(heading);
          if (!isCard && !heading.querySelector(".talk-title-rule")) {
            const rule = document.createElement("span");
            rule.className = "talk-title-rule";
            heading.appendChild(rule);
          }
        }
        const lis = [...section.querySelectorAll("li")].filter(
          (li) => !li.parentElement.closest("li"),
        );
        lis.forEach((li, i) => {
          li.classList.add("talk-bullet");
          li.dataset.talkBullet = String(i);
        });
        section.querySelectorAll(".cols > div").forEach((col, i) => {
          col.classList.add("talk-col");
          col.dataset.talkCol = String(i);
        });
        section.querySelectorAll("img").forEach((img, i) => {
          let wrap = img.closest(".talk-figure");
          if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "talk-figure";
            img.parentNode.insertBefore(wrap, img);
            wrap.appendChild(img);
          }
          wrap.dataset.talkFigure = String(i);
          img.classList.add("talk-figure-img");
        });
        if (
          section.querySelector("img") &&
          !["lead", "agenda", "card", "sources"].some((c) => section.classList.contains(c))
        ) {
          section.classList.add("talk-aroll");
        }
        section.querySelectorAll("strong, b").forEach((el, i) => {
          el.classList.add("talk-keyword");
          el.dataset.talkKeyword = String(i);
        });
        const punch =
          section.querySelector("blockquote") ||
          (section.classList.contains("accent")
            ? section.querySelector("p") ||
              section.querySelector("ul") ||
              heading
            : null) ||
          (section.classList.contains("card") ? heading : null);
        if (punch) punch.classList.add("talk-punch");
        root.dataset.talkSlide = String(slideIdx);
      });
      this.prepared = true;
    },

    _stateAt(t) {
      let slide = 0;
      let prevSlide = 0;
      let slideStart = 0;
      let titleOn = false;
      let titleStart = 0;
      const bullets = new Set();
      const keywords = new Set();
      const keywordStart = {};
      const cols = new Set();
      const figures = new Set();
      const figureStart = {};
      let punchOn = false;
      let punchStart = 0;
      let caption = "";
      let captionWords = [];
      let captionWord = -1;
      let count = null;
      let countStart = 0;
      let shot = null;
      const events = this.cues.events || [];
      for (const ev of events) {
        if (ev.t > t + 1e-9) break;
        if (ev.type === "slide") {
          if (ev.slide !== slide) prevSlide = slide;
          slide = ev.slide;
          slideStart = ev.t;
          titleOn = false;
          bullets.clear();
          keywords.clear();
          cols.clear();
          figures.clear();
          punchOn = false;
          caption = "";
          captionWords = [];
          captionWord = -1;
          count = null;
        } else if (ev.type === "title" && ev.slide === slide) {
          titleOn = true;
          titleStart = ev.t;
        } else if (ev.type === "bullet" && ev.slide === slide) {
          bullets.add(ev.i);
        } else if (ev.type === "col" && ev.slide === slide) {
          cols.add(ev.i);
        } else if (ev.type === "figure" && ev.slide === slide) {
          figures.add(ev.i);
          if (figureStart[ev.i] == null) figureStart[ev.i] = ev.t;
        } else if (ev.type === "keyword" && ev.slide === slide) {
          keywords.add(ev.i);
          if (keywordStart[ev.i] == null) keywordStart[ev.i] = ev.t;
        } else if (ev.type === "caption" && ev.slide === slide) {
          caption = String(ev.text || "");
          captionWords = Array.isArray(ev.words) ? ev.words.map(String) : [];
          captionWord = Number.isInteger(ev.i) ? ev.i : -1;
        } else if (ev.type === "word") {
          caption = String(ev.line || ev.text || caption);
          captionWords = Array.isArray(ev.words) ? ev.words.map(String) : caption.split(/\s+/).filter(Boolean);
          captionWord = Number.isInteger(ev.i) ? ev.i : captionWords.length - 1;
        } else if (ev.type === "punch" && ev.slide === slide) {
          punchOn = true;
          punchStart = ev.t;
        } else if (ev.type === "count" && ev.slide === slide) {
          count = ev;
          countStart = ev.t;
        } else if (ev.type === "shot") {
          shot = ev;
        }
      }
      const letterFrac = titleOn
        ? Math.min(1, Math.max(0, (t - titleStart) / TITLE_LETTER_S))
        : 0;
      const fade = slide !== prevSlide && t < slideStart + SLIDE_FADE_S
        ? Math.min(1, Math.max(0, (t - slideStart) / SLIDE_FADE_S))
        : 1;
      const meta = (this.cues.slides || [])[slide] || {};
      const slideDur = Math.max(
        0.5,
        (Number(meta.end_s) || slideStart + 8) - (Number(meta.start_s) || slideStart),
      );
      const kenBurns = Math.min(1, Math.max(0, (t - slideStart) / slideDur));
      return {
        slide, prevSlide, slideStart, titleOn, titleStart, letterFrac, fade, bullets,
        keywords, keywordStart, punchOn, punchStart, cols, figures, figureStart, kenBurns,
        caption, captionWords, captionWord, count, countStart, shot,
      };
    },

    _apply(state, t) {
      this.roots.forEach((root, i) => {
        const isCurr = i === state.slide;
        const isPrev = i === state.prevSlide && state.fade < 1 && i !== state.slide;
        const on = isCurr || isPrev;
        root.classList.toggle("talk-slide-on", on);
        root.classList.toggle("bespoke-marp-active", isCurr);
        root.classList.toggle("talk-slide-prev", isPrev);
        const yt = Boolean((this.cues || {}).youtube);
        const shotT = (state.shot && Number(state.shot.t)) || state.slideStart;
        const punchIn = yt && isCurr
          ? 1 + 0.05 * Math.min(1, Math.max(0, (t - shotT) / 0.28))
          : 1;
        if (isCurr && state.fade < 1) {
          root.style.opacity = String(state.fade);
          root.style.transform = `scale(${punchIn})`;
        } else if (isPrev) {
          root.style.opacity = String(1 - state.fade);
          root.style.transform = "none";
        } else if (isCurr) {
          root.style.opacity = "1";
          root.style.transform = `scale(${punchIn})`;
        } else {
          root.style.opacity = "";
          root.style.transform = "";
        }
        const section = this._sectionsIn(root);
        if (!section) return;
        const title = section.querySelector(".talk-title");
        if (title) {
          title.classList.toggle("is-on", isCurr && state.titleOn);
          const letters = [...title.querySelectorAll(".talk-letter")];
          const n = letters.length || 1;
          letters.forEach((span, idx) => {
            const last = Math.max(n - 1, 0);
            const letterOn = isCurr && state.titleOn && idx <= state.letterFrac * last;
            span.classList.toggle("is-on", letterOn);
            if (!span.classList.contains("talk-keyword-letter")) return;
            const strong = span.closest("strong, b");
            const ki = strong ? Number(strong.dataset.talkKeyword) : NaN;
            const kOn = letterOn && state.keywords.has(ki);
            const start = state.keywordStart[ki] ?? 0;
            const kFrac = kOn ? this._frac(t, start, KEYWORD_PUNCH_S) : 0;
            span.classList.toggle("is-punch", kOn && kFrac > 0);
            if (kOn) {
              span.style.transform = `scale(${0.96 + 0.12 * kFrac})`;
              span.style.color = "#d96b4c";
            } else {
              span.style.transform = "";
              span.style.color = "";
            }
          });
          const rule = title.querySelector(".talk-title-rule");
          if (rule) {
            const ruleFrac = isCurr && state.titleOn
              ? this._frac(t, state.titleStart + TITLE_LETTER_S, TITLE_RULE_S)
              : 0;
            rule.classList.toggle("is-on", ruleFrac > 0);
            rule.style.width = `${Math.round(ruleFrac * 1000) / 10}%`;
            rule.style.opacity = ruleFrac > 0 ? "1" : "0";
          }
        }
        section.querySelectorAll(".talk-bullet").forEach((li) => {
          const idx = Number(li.dataset.talkBullet);
          li.classList.toggle("is-on", isCurr && state.bullets.has(idx));
        });
        if (section.classList.contains("agenda")) {
          const ons = [...section.querySelectorAll(".talk-bullet.is-on")];
          ons.forEach((li, idx) => {
            li.classList.toggle("is-current", idx === ons.length - 1);
          });
          section.querySelectorAll(".talk-bullet:not(.is-on)").forEach((li) => {
            li.classList.remove("is-current");
          });
        }
        section.querySelectorAll(".talk-col").forEach((col) => {
          const idx = Number(col.dataset.talkCol);
          col.classList.toggle("is-on", isCurr && state.cols.has(idx));
        });
        section.querySelectorAll(".talk-figure").forEach((wrap) => {
          const idx = Number(wrap.dataset.talkFigure);
          const fOn = isCurr && state.figures.has(idx);
          const start = state.figureStart[idx] ?? state.slideStart;
          const fade = fOn ? this._frac(t, start, FIGURE_FADE_S) : 0;
          wrap.classList.toggle("is-on", fOn && fade > 0);
          wrap.style.opacity = fOn ? String(fade) : "0";
          const img = wrap.querySelector(".talk-figure-img, img");
          if (img) {
            const kb = fOn ? state.kenBurns : 0;
            const zoom = yt ? 0.16 : 0.08;
            img.style.transform = `scale(${1 + zoom * kb}) translate(${-10 * kb}px, ${-5 * kb}px)`;
          }
        });
        section.querySelectorAll(".talk-keyword").forEach((el) => {
          if (el.closest(".talk-title")) return;
          const ki = Number(el.dataset.talkKeyword);
          const kOn = isCurr && state.keywords.has(ki);
          const start = state.keywordStart[ki] ?? 0;
          const kFrac = kOn ? this._frac(t, start, KEYWORD_PUNCH_S) : 0;
          el.classList.toggle("is-on", kOn && kFrac > 0);
          if (kOn) {
            el.style.transform = `scale(${0.96 + 0.12 * kFrac})`;
            el.style.color = "#d96b4c";
          } else {
            el.style.transform = "";
            el.style.color = "";
          }
        });
        const punch = section.querySelector(".talk-punch");
        if (punch) {
          const pOn = isCurr && state.punchOn;
          const pFrac = pOn ? this._frac(t, state.punchStart, MERKSATZ_S) : 0;
          punch.classList.toggle("is-on", pOn && pFrac > 0);
          if (pOn) {
            const isCard = punch.classList.contains("talk-card-word");
            punch.style.transform = isCard
              ? `scale(${0.88 + 0.16 * pFrac})`
              : `scale(${0.96 + 0.04 * pFrac})`;
            if (!punch.querySelector(".talk-letter")) {
              punch.style.opacity = String(pFrac);
            }
          } else {
            punch.style.transform = "";
            if (!punch.querySelector(".talk-letter")) punch.style.opacity = "";
          }
        }
        section.querySelectorAll(".talk-count").forEach((el) => {
          const spec = isCurr ? state.count : null;
          const to = spec ? Number(spec.to) : Number(el.dataset.to || 0);
          const start = spec ? state.countStart : 0;
          const frac = spec ? this._frac(t, start, COUNT_S) : 0;
          el.textContent = this._formatCount(
            to, frac,
            Number(spec && spec.decimals != null ? spec.decimals : el.dataset.decimals || 0),
            (spec && spec.suffix) || el.dataset.suffix || "",
            (spec && spec.sep) || el.dataset.sep || ".",
          );
        });
      });
      const ytHud = Boolean((this.cues || {}).youtube);
      let bar = document.getElementById("talk-lower-third");
      if (!bar) {
        bar = document.createElement("div");
        bar.id = "talk-lower-third";
        document.body.appendChild(bar);
      }
      const cap = (state.caption || "").trim();
      bar.textContent = cap;
      bar.classList.toggle("is-on", Boolean(cap) && !ytHud);
      let chip = document.getElementById("talk-chapter-chip");
      if (!chip) {
        chip = document.createElement("div");
        chip.id = "talk-chapter-chip";
        document.body.appendChild(chip);
      }
      const slides = this.cues.slides || [];
      const meta = slides[state.slide] || {};
      const n = slides.length;
      const label = String(meta.chapter || meta.title || "").trim();
      const hideChip = n < 2 || meta.class_name === "lead";
      chip.textContent = label
        ? `${state.slide + 1} / ${n} · ${label}`
        : `${state.slide + 1} / ${n}`;
      const duration = Number((this.cues || {}).duration_s) || 0;
      const inHook = ytHud && (t < 5 || meta.class_name === "lead");
      const inTail = ytHud && duration > 0 && t >= duration - 2;
      chip.classList.toggle(
        "is-on",
        ytHud ? n >= 1 && !inHook && !inTail : !hideChip,
      );
      let layer = document.getElementById("talk-yt-shot");
      if (!layer) {
        layer = document.createElement("div");
        layer.id = "talk-yt-shot";
        document.body.appendChild(layer);
      }
      const sh = state.shot;
      const showShot = Boolean(sh && sh.kind !== "figure" && String(sh.text || "").trim());
      layer.textContent = showShot ? String(sh.text || "") : "";
      layer.dataset.kind = showShot ? String(sh.kind || "word") : "";
      layer.classList.toggle("is-on", showShot);
      let kara = document.getElementById("talk-karaoke");
      if (!kara) {
        kara = document.createElement("div");
        kara.id = "talk-karaoke";
        document.body.appendChild(kara);
      }
      const words = state.captionWords || [];
      const wi = Number(state.captionWord);
      if (ytHud && words.length) {
        kara.replaceChildren();
        words.forEach((w, idx) => {
          const span = document.createElement("span");
          span.className = "talk-kara-word";
          span.classList.toggle("is-on", idx <= wi);
          span.textContent = w;
          kara.appendChild(span);
          kara.appendChild(document.createTextNode(" "));
        });
        kara.classList.toggle("is-on", true);
      } else {
        kara.textContent = "";
        kara.classList.toggle("is-on", false);
      }
    },
  };

  window.TalkPresenter = TalkPresenter;
  const cueEl = document.getElementById("talk-cues");
  if (cueEl && cueEl.textContent.trim()) {
    try {
      TalkPresenter.load(JSON.parse(cueEl.textContent));
    } catch (err) {
      console.error("TalkPresenter: Cues unlesbar", err);
    }
  }
})();

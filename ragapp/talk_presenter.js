/**
 * Suchbarer Vortrags-Presenter. Zustand nur ueber Klassen/Inline-Styles (seek(t)).
 * window.TalkPresenter.load(cues); TalkPresenter.seek(seconds);
 */
(function () {
  const TITLE_LETTER_S = 0.4;
  const SLIDE_FADE_S = 0.55;

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
      const text = heading.textContent || "";
      heading.textContent = "";
      for (const ch of text) {
        const span = document.createElement("span");
        span.className = "talk-letter";
        span.textContent = ch === " " ? "\u00a0" : ch;
        heading.appendChild(span);
      }
      heading.dataset.talkWrapped = "1";
    },

    _prepare() {
      document.body.classList.add("talk-presenter-on");
      const svgs = [...document.querySelectorAll("svg.bespoke-marp-slide")];
      this.roots = svgs.length ? svgs : [...document.querySelectorAll("section")];
      this.roots.forEach((root, slideIdx) => {
        const section = this._sectionsIn(root);
        if (!section) return;
        const heading = section.querySelector("h1, h2, marp-h1, marp-h2");
        if (heading) {
          heading.classList.add("talk-title");
          this._wrapLetters(heading);
        }
        const lis = [...section.querySelectorAll("li")].filter(
          (li) => !li.parentElement.closest("li"),
        );
        lis.forEach((li, i) => {
          li.classList.add("talk-bullet");
          li.dataset.talkBullet = String(i);
        });
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
      const events = this.cues.events || [];
      for (const ev of events) {
        if (ev.t > t + 1e-9) break;
        if (ev.type === "slide") {
          if (ev.slide !== slide) prevSlide = slide;
          slide = ev.slide;
          slideStart = ev.t;
          titleOn = false;
          bullets.clear();
        } else if (ev.type === "title" && ev.slide === slide) {
          titleOn = true;
          titleStart = ev.t;
        } else if (ev.type === "bullet" && ev.slide === slide) {
          bullets.add(ev.i);
        }
      }
      const letterFrac = titleOn
        ? Math.min(1, Math.max(0, (t - titleStart) / TITLE_LETTER_S))
        : 0;
      const fade = slide !== prevSlide && t < slideStart + SLIDE_FADE_S
        ? Math.min(1, Math.max(0, (t - slideStart) / SLIDE_FADE_S))
        : 1;
      return { slide, prevSlide, slideStart, titleOn, letterFrac, fade, bullets };
    },

    _apply(state, t) {
      this.roots.forEach((root, i) => {
        const isCurr = i === state.slide;
        const isPrev = i === state.prevSlide && state.fade < 1 && i !== state.slide;
        const on = isCurr || isPrev;
        root.classList.toggle("talk-slide-on", on);
        root.classList.toggle("bespoke-marp-active", isCurr);
        root.classList.toggle("talk-slide-prev", isPrev);
        if (isCurr && state.fade < 1) {
          root.style.opacity = String(state.fade);
          root.style.transform = `translateX(${(1 - state.fade) * 36}px)`;
        } else if (isPrev) {
          root.style.opacity = String(1 - state.fade);
          root.style.transform = `translateX(${-state.fade * 28}px)`;
        } else if (isCurr) {
          root.style.opacity = "1";
          root.style.transform = "none";
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
            span.classList.toggle(
              "is-on",
              isCurr && state.titleOn && idx <= state.letterFrac * last,
            );
          });
        }
        section.querySelectorAll(".talk-bullet").forEach((li) => {
          const idx = Number(li.dataset.talkBullet);
          li.classList.toggle("is-on", isCurr && state.bullets.has(idx));
        });
      });
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

/**
 * Suchbarer Vortrags-Presenter. Zustand nur ueber Klassen (seek(t)).
 * window.TalkPresenter.load(cues); TalkPresenter.seek(seconds);
 */
(function () {
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
      this._apply(state);
      return this;
    },

    _sectionsIn(root) {
      if (root.tagName === "SECTION") return root;
      return root.querySelector("section");
    },

    _prepare() {
      document.body.classList.add("talk-presenter-on");
      const svgs = [...document.querySelectorAll("svg.bespoke-marp-slide")];
      this.roots = svgs.length ? svgs : [...document.querySelectorAll("section")];
      this.roots.forEach((root, slideIdx) => {
        const section = this._sectionsIn(root);
        if (!section) return;
        const heading = section.querySelector("h1, h2, marp-h1, marp-h2");
        if (heading) heading.classList.add("talk-title");
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
      let titleOn = false;
      const bullets = new Set();
      const events = this.cues.events || [];
      for (const ev of events) {
        if (ev.t > t + 1e-9) break;
        if (ev.type === "slide") {
          slide = ev.slide;
          titleOn = false;
          bullets.clear();
        } else if (ev.type === "title" && ev.slide === slide) {
          titleOn = true;
        } else if (ev.type === "bullet" && ev.slide === slide) {
          bullets.add(ev.i);
        }
      }
      return { slide, titleOn, bullets };
    },

    _apply(state) {
      this.roots.forEach((root, i) => {
        const on = i === state.slide;
        root.classList.toggle("talk-slide-on", on);
        root.classList.toggle("bespoke-marp-active", on);
        const section = this._sectionsIn(root);
        if (!section) return;
        const title = section.querySelector(".talk-title");
        if (title) title.classList.toggle("is-on", on && state.titleOn);
        section.querySelectorAll(".talk-bullet").forEach((li) => {
          const idx = Number(li.dataset.talkBullet);
          li.classList.toggle("is-on", on && state.bullets.has(idx));
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

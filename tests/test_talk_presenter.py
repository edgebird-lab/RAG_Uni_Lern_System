"""Presenter: seek(t) blendet Titel/Bullets suchbar ein."""
from __future__ import annotations

from pathlib import Path

from ragapp.talk_cues import build_talk_cues
from ragapp.talk_presenter import inject_talk_presenter

FIXTURE = Path("tests/fixtures/talk_presenter.html")
MARP = """\
---
marp: true
---

<!-- _class: lead -->

# Lernvortrag Testing

---

<!-- _class: agenda -->

## Heute lernen wir

1. Begriff klären
2. Beispiel durchgehen
"""


def test_inject_talk_presenter_keeps_download_html_untouched():
    raw = FIXTURE.read_text(encoding="utf-8")
    cues = build_talk_cues(MARP, duration_s=8.0)
    out = inject_talk_presenter(raw, cues)
    assert "talk-presenter-css" in out
    assert "TalkPresenter" in out
    assert raw.count("TalkPresenter") == 0
    assert "</body>" in out


def test_seek_reveals_title_then_bullets(tmp_path):
    from playwright.sync_api import sync_playwright

    cues = build_talk_cues(MARP, duration_s=8.0)
    html = inject_talk_presenter(FIXTURE.read_text(encoding="utf-8"), cues)
    path = tmp_path / "presenter.html"
    path.write_text(html, encoding="utf-8")

    agenda = next(s for s in cues["slides"] if s["class_name"] == "agenda")
    first_bullet_t = next(e["t"] for e in agenda["events"] if e.get("i") == 0)
    before_bullet = max(agenda["start_s"], first_bullet_t - 0.05)
    after_bullet = first_bullet_t + 0.02

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")

        page.evaluate("t => window.TalkPresenter.seek(t)", 0)
        assert page.locator("section.lead .talk-title.is-on").count() == 1
        assert page.locator("section.agenda.talk-slide-on").count() == 0
        assert page.locator(".talk-bullet.is-on").count() == 0

        page.evaluate("t => window.TalkPresenter.seek(t)", before_bullet)
        assert page.locator("section.agenda .talk-title.is-on").count() == 1
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 0

        page.evaluate("t => window.TalkPresenter.seek(t)", after_bullet)
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 1

        page.evaluate("t => window.TalkPresenter.seek(t)", 7.9)
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 2
        browser.close()


MOTION_MARP = """\
---
marp: true
---

<!-- _class: lead -->

# Lernvortrag **Testing**

---

<!-- _class: accent -->

## Merksatz

> Abrufen schlägt Nachlesen.

---

<!-- _class: content -->

## Kern

- Der **Testing-Effekt** bleibt
"""


def test_seek_keyword_and_merksatz_punch(tmp_path):
    from playwright.sync_api import sync_playwright

    motion = Path("tests/fixtures/talk_presenter_motion.html")
    cues = build_talk_cues(MOTION_MARP, duration_s=9.0)
    # unknown event types must be ignored
    cues["events"].append({"t": 0.05, "type": "nope", "slide": 0})
    cues["events"].sort(key=lambda e: e["t"])
    html = inject_talk_presenter(motion.read_text(encoding="utf-8"), cues)
    path = tmp_path / "motion.html"
    path.write_text(html, encoding="utf-8")

    lead = cues["slides"][0]
    accent = cues["slides"][1]
    content = cues["slides"][2]
    kw0 = next(e for e in lead["events"] if e["type"] == "keyword")
    punch = next(e for e in accent["events"] if e["type"] == "punch")
    kw_bullet = next(e for e in content["events"] if e["type"] == "keyword")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")

        page.evaluate("t => window.TalkPresenter.seek(t)", 0)
        assert page.locator("section.lead .talk-keyword-letter").count() >= 4
        assert page.locator("section.lead .talk-keyword-letter.is-punch").count() == 0

        page.evaluate("t => window.TalkPresenter.seek(t)", kw0["t"] + 0.45)
        assert page.locator("section.lead .talk-keyword-letter.is-punch").count() >= 4

        page.evaluate("t => window.TalkPresenter.seek(t)", max(0.0, accent["start_s"] - 0.05))
        assert page.locator("section.accent.talk-slide-on").count() == 0

        page.evaluate("t => window.TalkPresenter.seek(t)", punch["t"] + 0.4)
        assert page.locator("section.accent .talk-punch.is-on").count() == 1
        scale = page.locator("section.accent .talk-punch").evaluate(
            "el => el.style.transform")
        assert "scale" in scale

        page.evaluate("t => window.TalkPresenter.seek(t)", kw_bullet["t"] + 0.4)
        assert page.locator("section.content .talk-keyword.is-on").count() == 1
        browser.close()


def test_seek_title_letters_and_slide_fade(tmp_path):
    from playwright.sync_api import sync_playwright

    cues = build_talk_cues(MARP, duration_s=8.0)
    html = inject_talk_presenter(FIXTURE.read_text(encoding="utf-8"), cues)
    path = tmp_path / "presenter.html"
    path.write_text(html, encoding="utf-8")
    agenda = next(s for s in cues["slides"] if s["class_name"] == "agenda")
    first_bullet_t = next(e["t"] for e in agenda["events"] if e.get("i") == 0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")

        page.evaluate("t => window.TalkPresenter.seek(t)", 0)
        letters = page.locator("section.lead .talk-letter")
        on0 = page.locator("section.lead .talk-letter.is-on").count()
        assert letters.count() >= 4
        assert 0 < on0 < letters.count()

        page.evaluate("t => window.TalkPresenter.seek(t)", 0.45)
        assert page.locator("section.lead .talk-letter.is-on").count() == letters.count()
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 0

        page.evaluate("t => window.TalkPresenter.seek(t)", agenda["start_s"] + 0.1)
        assert page.locator("section.agenda.talk-slide-on").count() == 1
        assert page.locator("section.lead.talk-slide-prev").count() == 1
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 0
        assert first_bullet_t > agenda["start_s"]
        browser.close()

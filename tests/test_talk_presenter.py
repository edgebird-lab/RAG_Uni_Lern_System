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

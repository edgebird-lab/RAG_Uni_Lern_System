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
        assert page.locator("section.agenda .talk-bullet.is-current").count() == 1

        page.evaluate("t => window.TalkPresenter.seek(t)", 7.9)
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 2
        current = page.locator("section.agenda .talk-bullet.is-current")
        assert current.count() == 1
        assert current.inner_text().startswith("Beispiel")
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
    first_bullet_t = next(
        e["t"] for e in agenda["events"]
        if e.get("type") == "bullet" and e.get("i") == 0)

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
        rule_w = page.locator("section.lead .talk-title-rule").evaluate("el => el.style.width")
        assert rule_w.endswith("%")
        assert float(rule_w[:-1]) > 0

        page.evaluate("t => window.TalkPresenter.seek(t)", agenda["start_s"] + 0.02)
        assert page.locator("section.agenda.talk-slide-on").count() == 1
        agenda_tx = page.locator("section.agenda").evaluate("el => el.style.transform")
        lead_tx = page.locator("section.lead").evaluate("el => el.style.transform")
        assert "translateX" not in (agenda_tx or "")
        assert "translateX" not in (lead_tx or "")

        page.evaluate("t => window.TalkPresenter.seek(t)", agenda["start_s"] + 0.12)
        assert page.locator("section.agenda.talk-slide-on").count() == 1
        assert page.locator("section.lead.talk-slide-prev").count() == 0
        assert page.locator("section.lead.talk-slide-on").count() == 0
        assert page.locator("section.agenda .talk-bullet.is-on").count() == 0
        assert first_bullet_t > agenda["start_s"]
        browser.close()


SPLIT_MARP = """\
---
marp: true
---

<!-- _class: split -->

## Vergleich

<div class="cols">
<div>

### Abrufen

- Karten
</div>
<div>

### Nachlesen

- Skript
</div>
</div>
"""


def test_seek_split_columns(tmp_path):
    from playwright.sync_api import sync_playwright

    html_src = """<!DOCTYPE html><html><body>
<section class="split">
  <h2>Vergleich</h2>
  <div class="cols">
    <div><h3>Abrufen</h3><ul><li>Karten</li></ul></div>
    <div><h3>Nachlesen</h3><ul><li>Skript</li></ul></div>
  </div>
</section>
</body></html>"""
    cues = build_talk_cues(SPLIT_MARP, duration_s=6.0)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "split.html"
    path.write_text(html, encoding="utf-8")
    col1 = next(e for e in cues["events"] if e["type"] == "col" and e["i"] == 1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", 0.05)
        assert page.locator(".talk-col.is-on").count() == 1
        page.evaluate("t => window.TalkPresenter.seek(t)", col1["t"] + 0.05)
        assert page.locator(".talk-col.is-on").count() == 2
        browser.close()


def test_seek_figure_ken_burns(tmp_path):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    import re

    png = tmp_path / "fig.png"
    Image.new("RGB", (64, 48), (200, 80, 40)).save(png)

    html_src = f"""<!DOCTYPE html><html><body>
<section class="content">
  <h2>Kern</h2>
  <ul><li>Punkt</li></ul>
  <p><img src="{png.as_uri()}" alt="Abbildung"></p>
</section>
</body></html>"""
    md = """\
---
marp: true
---

<!-- _class: content -->

## Kern

- Punkt

![Abbildung](figures/p1.png)
"""
    cues = build_talk_cues(md, duration_s=8.0)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "fig.html"
    path.write_text(html, encoding="utf-8")
    fig_t = next(e["t"] for e in cues["events"] if e["type"] == "figure")

    def scale_of(s: str) -> float:
        m = re.search(r"scale\(([-0-9.]+)\)", s)
        return float(m.group(1)) if m else 0.0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", 0)
        op0 = float(page.locator(".talk-figure").evaluate("el => el.style.opacity || '0'"))
        assert op0 == 0
        page.evaluate("t => window.TalkPresenter.seek(t)", fig_t + 0.5)
        op1 = float(page.locator(".talk-figure").evaluate("el => el.style.opacity || '0'"))
        assert op1 > 0.8
        early = page.locator(".talk-figure-img").evaluate("el => el.style.transform")
        page.evaluate("t => window.TalkPresenter.seek(t)", 7.5)
        late = page.locator(".talk-figure-img").evaluate("el => el.style.transform")
        assert scale_of(late) > scale_of(early)
        assert page.locator("section.talk-aroll").count() == 1
        box = page.locator(".talk-figure").bounding_box()
        assert box is not None
        assert box["width"] >= 1200
        assert box["height"] >= 680
        display = page.locator(".talk-bullet").evaluate("el => getComputedStyle(el).display")
        assert display == "none"
        title_pos = page.locator("section.talk-aroll .talk-title").evaluate(
            "el => getComputedStyle(el).position")
        assert title_pos == "absolute"
        browser.close()


def test_seek_lower_third_caption(tmp_path):
    from playwright.sync_api import sync_playwright
    from ragapp.talk_cues import map_timeline_to_cues

    html_src = """<!DOCTYPE html><html><body>
<section class="accent"><h2>Merksatz</h2><blockquote>Abrufen schlägt Nachlesen.</blockquote></section>
</body></html>"""
    md = "<!-- _class: accent -->\n\n## Merksatz\n\n> Abrufen schlägt Nachlesen.\n"
    timeline = [
        {"index": 0, "text": "Merksatz Overlay.", "start_s": 0.0, "duration_s": 1.0},
        {"index": 1, "text": "Zweiter Satz ohne Overlay.", "start_s": 2.0, "duration_s": 1.0},
    ]
    cues = map_timeline_to_cues(md, timeline)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "cap.html"
    path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", 0.2)
        bar = page.locator("#talk-lower-third")
        assert bar.count() == 1
        assert "Merksatz" in bar.inner_text()
        assert bar.evaluate("el => el.classList.contains('is-on')")
        page.evaluate("t => window.TalkPresenter.seek(t)", 2.1)
        assert "Merksatz" in bar.inner_text()
        assert "Zweiter" not in bar.inner_text()
        browser.close()


def test_seek_card_word_scales_full_bleed(tmp_path):
    from playwright.sync_api import sync_playwright

    md = """\
---
marp: true
---

<!-- _class: card -->

## **Grounding**
"""
    html_src = """<!DOCTYPE html><html><body>
<section class="card"><h2><strong>Grounding</strong></h2></section>
</body></html>"""
    cues = build_talk_cues(md, duration_s=4.0)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "card.html"
    path.write_text(html, encoding="utf-8")
    punch = next(e for e in cues["events"] if e["type"] == "punch")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", 0)
        assert page.locator("section.card .talk-card-word").count() == 1
        assert page.locator("section.card .talk-title-rule").count() == 0
        page.evaluate("t => window.TalkPresenter.seek(t)", punch["t"] + 0.4)
        word = page.locator("section.card .talk-card-word")
        assert word.evaluate("el => el.classList.contains('talk-punch')")
        assert word.evaluate("el => el.classList.contains('is-on')")
        scale = word.evaluate("el => el.style.transform")
        assert "scale" in scale
        font = word.evaluate("el => getComputedStyle(el).fontSize")
        assert float(font.replace("px", "")) >= 48
        browser.close()


def test_seek_count_up_and_chapter_chip(tmp_path):
    from playwright.sync_api import sync_playwright

    md = """\
---
marp: true
---

<!-- _class: lead -->

# Start

---

<!-- _class: agenda -->

## Heute lernen wir

1. Grounding
2. Prozent

---

<!-- _class: card -->

## **42 %**
"""
    html_src = """<!DOCTYPE html><html><body>
<section class="lead"><h1>Start</h1></section>
<section class="agenda"><h2>Heute lernen wir</h2><ol><li>Grounding</li><li>Prozent</li></ol></section>
<section class="card"><h2><strong>42 %</strong></h2></section>
</body></html>"""
    cues = build_talk_cues(md, duration_s=9.0)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "count.html"
    path.write_text(html, encoding="utf-8")
    card = next(s for s in cues["slides"] if s["class_name"] == "card")
    count_t = next(e["t"] for e in card["events"] if e["type"] == "count")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")

        page.evaluate("t => window.TalkPresenter.seek(t)", 0)
        assert page.locator("#talk-chapter-chip.is-on").count() == 0

        page.evaluate("t => window.TalkPresenter.seek(t)", count_t)
        early = page.locator("section.card .talk-count").inner_text()
        page.evaluate("t => window.TalkPresenter.seek(t)", count_t + 0.75)
        late = page.locator("section.card .talk-count").inner_text()
        assert early.startswith("0")
        assert "42" in late
        chip = page.locator("#talk-chapter-chip")
        assert chip.evaluate("el => el.classList.contains('is-on')")
        text = chip.inner_text()
        assert "3 / 3" in text
        assert "grounding" in text.lower()
        browser.close()


def test_seek_youtube_shot_overlay_changes(tmp_path):
    from playwright.sync_api import sync_playwright
    from ragapp.talk_cues import load_talk_cues

    md = """\
<!-- _class: accent -->

## Merksatz eins

---

<!-- _class: accent -->

## Merksatz zwei
"""
    html_src = """<!DOCTYPE html><html><body>
<section class="accent"><h2>Merksatz eins</h2></section>
<section class="accent"><h2>Merksatz zwei</h2></section>
</body></html>"""
    timeline = [
        {"index": 0, "text": "Grounding heißt nur schreiben was da steht.",
         "start_s": 0.0, "duration_s": 3.0},
        {"index": 1, "text": "Spaced Repetition hält das Gelernte.",
         "start_s": 6.0, "duration_s": 3.0},
    ]
    cues = load_talk_cues(md, duration_s=12.0, timeline=timeline, youtube=True)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "yt.html"
    path.write_text(html, encoding="utf-8")
    shots = [e for e in cues["events"] if e["type"] == "shot"]
    assert len(shots) >= 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", 0.05)
        layer = page.locator("#talk-yt-shot")
        assert not layer.evaluate("el => el.classList.contains('is-on')")
        late = next(e for e in shots if e["t"] >= 5.0)
        page.evaluate("t => window.TalkPresenter.seek(t)", late["t"] + 0.05)
        assert layer.evaluate("el => el.classList.contains('is-on')")
        box = layer.bounding_box()
        assert box is not None
        assert box["height"] < 280
        assert box["y"] < 200
        assert layer.inner_text().strip()
        assert "bestehen" not in layer.inner_text().lower()
        chip = page.locator("#talk-chapter-chip")
        page.evaluate("t => window.TalkPresenter.seek(t)", 6.0)
        assert chip.evaluate("el => el.classList.contains('is-on')")
        browser.close()


def test_seek_youtube_hides_shot_on_lead(tmp_path):
    from playwright.sync_api import sync_playwright
    from ragapp.talk_cues import load_talk_cues

    md = """\
<!-- _class: lead -->

# **Livetest** Die Kraft der aktiven Wiederholung
"""
    html_src = """<!DOCTYPE html><html><body>
<section class="lead"><h1>Livetest Die Kraft der aktiven Wiederholung</h1></section>
</body></html>"""
    timeline = [
        {"index": 0, "text": "Hast du schon einmal versucht, die Lernstoffkarten zu wiederholen?",
         "start_s": 0.4, "duration_s": 3.0},
    ]
    cues = load_talk_cues(md, duration_s=8.0, timeline=timeline, youtube=True)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "lead.html"
    path.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 900, "height": 500})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", 1.0)
        layer = page.locator("#talk-yt-shot")
        assert not layer.evaluate("el => el.classList.contains('is-on')")
        words = page.locator("h1 .talk-word")
        assert words.count() >= 4
        wieder = page.locator("h1 .talk-word").filter(has_text="Wiederholung")
        assert wieder.count() >= 1
        box = wieder.first.bounding_box()
        assert box is not None
        assert box["height"] < 90
        browser.close()


def test_seek_youtube_karaoke_highlights_words(tmp_path):
    from playwright.sync_api import sync_playwright
    from ragapp.talk_cues import load_talk_cues

    md = "<!-- _class: card -->\n\n## **Grounding**\n"
    html_src = """<!DOCTYPE html><html><body>
<section class="card"><h2>Grounding</h2></section>
</body></html>"""
    timeline = [
        {"index": 0, "text": "Abrufen schlägt Nachlesen.",
         "start_s": 0.5, "duration_s": 1.8},
    ]
    cues = load_talk_cues(md, duration_s=4.0, timeline=timeline, youtube=True)
    html = inject_talk_presenter(html_src, cues)
    path = tmp_path / "kara.html"
    path.write_text(html, encoding="utf-8")
    words = [e for e in cues["events"] if e["type"] == "word"]
    assert len(words) >= 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("window.TalkPresenter && window.TalkPresenter.prepared")
        page.evaluate("t => window.TalkPresenter.seek(t)", words[0]["t"] + 0.02)
        kara = page.locator("#talk-karaoke")
        assert kara.evaluate("el => el.classList.contains('is-on')")
        first_on = kara.locator(".talk-kara-word.is-on").count()
        page.evaluate("t => window.TalkPresenter.seek(t)", words[-1]["t"] + 0.02)
        last_on = kara.locator(".talk-kara-word.is-on").count()
        assert first_on >= 1
        assert last_on >= first_on
        assert "Nachlesen" in kara.inner_text()
        browser.close()

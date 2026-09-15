"""Tests fuer ragapp.talk_cues: Marp → suchbare Eventliste."""
from __future__ import annotations

from ragapp.talk_cues import (
    build_talk_cues,
    parse_slide_body,
    split_marp_slides,
)


FIXTURE_MD = """\
---
marp: true
paginate: true
---

<!-- _class: lead -->

# Lernvortrag Testing

---

<!-- _class: agenda -->

## Heute lernen wir

1. Begriff klären
2. Beispiel durchgehen
3. Kurz üben

---

<!-- _class: content -->

## Kernidee

- Erster Punkt
- Zweiter Punkt

Ein Satz ohne Listenmarker bleibt unsichtbar für Cues.
"""


def test_split_marp_slides_strips_frontmatter():
    slides = split_marp_slides(FIXTURE_MD)
    assert len(slides) == 3
    assert "_class: lead" in slides[0]
    assert "Heute lernen wir" in slides[1]


def test_parse_slide_extracts_class_title_bullets():
    slides = split_marp_slides(FIXTURE_MD)
    lead = parse_slide_body(slides[0])
    assert lead["class_name"] == "lead"
    assert lead["title"] == "Lernvortrag Testing"
    assert lead["bullets"] == []

    agenda = parse_slide_body(slides[1])
    assert agenda["class_name"] == "agenda"
    assert agenda["title"] == "Heute lernen wir"
    assert agenda["bullets"] == [
        "Begriff klären", "Beispiel durchgehen", "Kurz üben"]

    content = parse_slide_body(slides[2])
    assert content["class_name"] == "content"
    assert "Erster Punkt" in content["bullets"]
    assert len(content["bullets"]) == 2


def test_build_talk_cues_placeholder_timing():
    cues = build_talk_cues(FIXTURE_MD, duration_s=12.0)
    assert cues["version"] == 1
    assert cues["width"] == 1280
    assert cues["height"] == 720
    assert cues["duration_s"] == 12.0
    assert cues["source"] == "placeholder"
    assert len(cues["slides"]) == 3

    times = [e["t"] for e in cues["events"]]
    assert times == sorted(times)
    assert times[0] == 0.0
    assert cues["events"][-1]["t"] < 12.0

    lead = cues["slides"][0]
    types = [e["type"] for e in lead["events"]]
    assert types == ["slide", "title"]
    assert lead["start_s"] == 0.0
    assert lead["end_s"] == 4.0

    agenda = cues["slides"][1]
    assert [e["type"] for e in agenda["events"]] == [
        "slide", "title", "bullet", "bullet", "bullet"]
    bullets = [e for e in agenda["events"] if e["type"] == "bullet"]
    assert [e["i"] for e in bullets] == [0, 1, 2]
    title_t = next(e["t"] for e in agenda["events"] if e["type"] == "title")
    assert bullets[0]["t"] > title_t
    assert bullets[0]["t"] >= agenda["start_s"] + 0.39
    assert bullets[-1]["t"] < agenda["end_s"]


def test_build_talk_cues_empty_md_gets_one_slide():
    cues = build_talk_cues("", duration_s=5)
    assert len(cues["slides"]) == 1
    assert cues["duration_s"] == 5.0


def test_link_and_emphasis_stripped_from_bullets():
    md = """---
marp: true
---

## Titel

- Siehe [Paper](https://example.com) **wichtig**
"""
    parsed = parse_slide_body(split_marp_slides(md)[0])
    assert parsed["bullets"] == ["Siehe Paper wichtig"]

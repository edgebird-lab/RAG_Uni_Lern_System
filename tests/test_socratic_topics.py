"""Themenvorschläge für den sokratischen Dialog: Stoff, keine Dateinamen."""
from ragapp.graph.socratic import (
    collect_socratic_topic_suggestions, is_usable_topic, topic_from_front,
    topics_from_markdown,
)


def test_topic_from_front_zieht_begriff_aus_definitionsfrage():
    assert topic_from_front("Was ist der Testing-Effekt?") == "Testing-Effekt"
    assert topic_from_front("Was ist Spaced Repetition?") == "Spaced Repetition"
    assert topic_from_front(
        "Was bedeutet Grounding in diesem System?") == "Grounding"
    assert topic_from_front("Ableitung von $f(x)=x^2$?") == "Ableitung"
    assert topic_from_front(
        "Livetest: Was ist der Testing-Effekt?", subject="Livetest"
    ) == "Testing-Effekt"


def test_topic_from_front_laesst_offene_wie_fragen_weg():
    assert topic_from_front(
        "Welche drei Schritte hat die Analysis-Anleitung?") == ""


def test_is_usable_topic_filtert_dateinamen_und_fachlabel():
    stems = ["Livetest_Definitionen", "Livetest_Formeln"]
    assert is_usable_topic("Testing-Effekt", subject="Livetest",
                           filename_stems=stems)
    assert not is_usable_topic("Livetest", subject="Livetest",
                               filename_stems=stems)
    assert not is_usable_topic("Livetest_Definitionen", subject="Livetest",
                               filename_stems=stems)
    assert not is_usable_topic("Definitionen", subject="Livetest",
                               filename_stems=stems)
    assert not is_usable_topic("Anleitung", subject="Livetest")
    assert not is_usable_topic("Seite 7")
    assert not is_usable_topic("Folie 3")
    assert not is_usable_topic("Page 12")
    from ragapp.graph.socratic import is_page_label
    assert is_page_label("Seite 7")
    assert is_page_label("Folie 3")
    assert is_page_label("Page 12")
    assert not is_page_label("Testing-Effekt")
    assert not is_page_label("Seite zwei")


def test_collect_nimmt_karten_themen_nicht_dateinamen():
    cards = [
        {"topic": "Testing-Effekt", "front": "Was ist der Testing-Effekt?"},
        {"topic": "Spaced Repetition", "front": "Was ist Spaced Repetition?"},
        {"topic": "Grounding", "front": "Was bedeutet Grounding in diesem System?"},
        {"topic": "Anleitung", "front": "Welche drei Schritte hat die Analysis-Anleitung?"},
        {"topic": "Ableitung", "front": r"Ableitung von $f(x)=x^2$?"},
    ]
    docs = [
        {"subject": "Livetest", "filename": "Livetest_Definitionen.md",
         "source_path": "tests/fixtures/livetest/Livetest_Definitionen.md"},
        {"subject": "Livetest", "filename": "Livetest_Formeln.md",
         "source_path": "tests/fixtures/livetest/Livetest_Formeln.md"},
    ]
    out = collect_socratic_topic_suggestions(
        cards=cards, documents=docs, subject="Livetest")
    assert "Livetest_Definitionen" not in out
    assert "Livetest" not in out
    assert out[:3] == ["Testing-Effekt", "Spaced Repetition", "Grounding"]
    assert "Ableitung" in out
    assert "Anleitung" not in out


def test_collect_nimmt_nummerierte_und_extra_ueberschriften():
    md = "1. Testing-Effekt\n\nText\n\n2. Spaced Repetition\n"
    out = collect_socratic_topic_suggestions(
        cards=[], documents=[], extra_headings=["Grounding"])
    assert out == ["Grounding"]
    from ragapp.graph.socratic import topics_from_markdown
    heads = topics_from_markdown(md)
    assert "Testing-Effekt" in heads
    assert "Spaced Repetition" in heads
    md = (
        "# Livetest: Begriffskarten\n\n"
        "## Testing-Effekt\n\nText\n\n"
        "## Spaced Repetition\n\nText\n"
    )
    docs = [{"subject": "Livetest", "filename": "Livetest_Definitionen.md",
             "source_path": "def.md"}]
    out = collect_socratic_topic_suggestions(
        cards=[], documents=docs, subject="Livetest",
        read_text=lambda p: md if p == "def.md" else "")
    assert out == ["Testing-Effekt", "Spaced Repetition"]
    assert topics_from_markdown(md, subject="Livetest") == out

    mixed = collect_socratic_topic_suggestions(
        cards=[], documents=docs, subject="Livetest",
        read_text=lambda p: md if p == "def.md" else "",
        extra_headings=["Seite 7", "Grounding", "Folie 2"],
    )
    assert mixed[0] == "Testing-Effekt"
    assert "Seite 7" not in mixed
    assert "Folie 2" not in mixed
    assert "Grounding" in mixed

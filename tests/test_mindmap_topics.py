"""Mindmap-Themenhelfer: Anzeigenamen, Teilbaum, Quellenauszuege.

Isoliert geladen (kein Vollimport von ``ragapp.mindmap``), analog zu
``test_mindmap_generate.py``.
"""
import re

import pytest


@pytest.fixture
def topic_funcs(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "mindmap.py",
        ["display_title", "node_label", "topic_subtree_ids", "topic_indices",
         "excerpts_for_indices"],
        {"re": re},
        const_names=["_GENERIC_TITLE_RE"],
    )


def _graph():
    return {
        "root": "Fach",
        "nodes": [
            {"id": "n1", "title": "Seite 3", "parent": None, "indices": [0]},
            {"id": "n2", "title": "Sortieren", "parent": None, "indices": [1]},
            {"id": "n3", "title": "QuickSort", "parent": "n2", "indices": [2]},
            {"id": "n4", "title": "Pivot", "parent": "n3", "indices": [3]},
        ],
        "links": [],
    }


def test_display_title_ersetzt_generische_seiten_titel(topic_funcs):
    fn = topic_funcs["display_title"]
    out = fn("Seite 12", "Hashfunktionen speichern Schlüssel in Buckets und lösen Kollisionen.")
    assert out != "Seite 12"
    assert "Hashfunktionen" in out
    assert fn("Folie 3", "a b c d e") != "Folie 3"
    assert fn("Page 7", "alpha beta gamma") != "Page 7"


def test_display_title_laesst_echte_themen_unveraendert(topic_funcs):
    fn = topic_funcs["display_title"]
    assert fn("Hashfunktionen", "Seite 12 irgendwas") == "Hashfunktionen"
    assert fn("Sortieren", "") == "Sortieren"


def test_display_title_behaelt_seite_wenn_text_zu_kurz(topic_funcs):
    fn = topic_funcs["display_title"]
    assert fn("Seite 1", "kurz") == "Seite 1"


def test_node_label_zieht_koerper_aus_toc_indizes(topic_funcs):
    fn = topic_funcs["node_label"]
    sections = [("d.pdf", "Seite 3", "Kollisionen werden mit Verkettung aufgelöst extra.")]
    node = {"id": "n1", "title": "Seite 3", "indices": [0]}
    assert "Kollisionen" in fn(node, sections)


def test_topic_subtree_ids_enthaelt_knoten_und_nachfahren(topic_funcs):
    fn = topic_funcs["topic_subtree_ids"]
    ids = fn(_graph(), "n2")
    assert ids[0] == "n2"
    assert set(ids) == {"n2", "n3", "n4"}
    assert fn(_graph(), "n1") == ["n1"]


def test_topic_indices_sammelt_belege_ohne_duplikate(topic_funcs):
    fn = topic_funcs["topic_indices"]
    graph = _graph()
    assert fn(graph, ["n2"], include_children=True) == [1, 2, 3]
    assert fn(graph, ["n2"], include_children=False) == [1]
    assert fn(graph, ["n2", "n3"], include_children=True) == [1, 2, 3]


def test_excerpts_for_indices_nutzt_anzeigenamen_und_cap(topic_funcs):
    fn = topic_funcs["excerpts_for_indices"]
    sections = [
        ("a.pdf", "Seite 1", "Erster Abschnitt mit genug Text zum Anzeigenamen bilden."),
        ("a.pdf", "Sortieren", "QuickSort teilt das Feld am Pivot."),
    ]
    out = fn(sections, [0, 1], max_chars=2000)
    assert "Seite 1" not in out
    assert "Erster Abschnitt" in out
    assert "QuickSort" in out
    assert "**Sortieren**" in out

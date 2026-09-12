"""Tests für _notes_to_markdown() auf der Notizen-Seite (bündelt gefilterte
Notizen zu einem Markdown-Export). Isoliert geladen (kein Vollimport der
Streamlit-Seite nötig für eine reine Formatierungsfunktion)."""
from __future__ import annotations

import types

import pytest


@pytest.fixture
def notes_to_markdown(load_functions, ragapp_dir):
    fake_settings = types.SimpleNamespace(SUBJECT_LABELS={"mathe": "Mathematik"})
    funcs = load_functions(
        ragapp_dir / "ui" / "pages" / "12_🗒️_Notizen.py",
        ["_fach", "_notes_to_markdown"],
        {"SUBJECT_LABELS": fake_settings.SUBJECT_LABELS},
    )
    return funcs["_notes_to_markdown"]


def test_notes_to_markdown_eine_notiz(notes_to_markdown):
    notes = [{"title": "FSRS", "subject": "mathe", "body": "Wiederholungsalgorithmus.",
             "updated_at": 1700000000.0}]
    out = notes_to_markdown(notes)
    assert out.startswith("# FSRS")
    assert "Mathematik" in out
    assert "Wiederholungsalgorithmus." in out


def test_notes_to_markdown_mehrere_notizen_getrennt_durch_trenner(notes_to_markdown):
    notes = [
        {"title": "Erste", "subject": "mathe", "body": "Text 1", "updated_at": 1700000000.0},
        {"title": "Zweite", "subject": "mathe", "body": "Text 2", "updated_at": 1700000000.0},
    ]
    out = notes_to_markdown(notes)
    assert out.count("\n\n---\n\n") == 1
    assert "Erste" in out and "Zweite" in out


def test_notes_to_markdown_ohne_titel_zeigt_platzhalter(notes_to_markdown):
    notes = [{"title": "", "subject": None, "body": "Text", "updated_at": 1700000000.0}]
    out = notes_to_markdown(notes)
    assert "(ohne Titel)" in out
    assert "ohne Fach" in out


def test_notes_to_markdown_leere_liste_ist_leerer_string(notes_to_markdown):
    assert notes_to_markdown([]) == ""

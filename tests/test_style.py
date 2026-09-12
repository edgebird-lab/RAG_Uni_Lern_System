"""Tests fuer ragapp.ui._style: reine String/Dict-Logik (kein Streamlit-Rendering).

Fokus dieser Datei: die "technische" Design-Variante fuer Evaluation/
Einstellungen (siehe TECHNICAL_PAGE_KEYS/_technical_override_css) - die
Betreiber-/Admin-Seiten sollen KEINE Doodles und eine entsaettigte, sachlichere
Karten-/Titel-Optik bekommen statt der verspielten "Cozy Kawaii"-Basis-Optik.
"""
from __future__ import annotations

from ragapp.ui._style import (
    PAGE_THEMES,
    TECHNICAL_PAGE_KEYS,
    _doodle_layer,
    _technical_override_css,
    theme_for,
)


def test_technical_page_keys_enthaelt_nur_evaluation_und_einstellungen():
    assert TECHNICAL_PAGE_KEYS == {"evaluation", "einstellungen"}


def test_technical_page_keys_sind_bekannte_themen():
    for key in TECHNICAL_PAGE_KEYS:
        assert key in PAGE_THEMES


def test_lern_und_erstellen_seiten_sind_nicht_technisch():
    for key in ("home", "chat", "lernen", "mindmap", "uebungsaufgaben",
                "lernplan", "zusammenfassung", "audio", "notizen",
                "fortschritt", "lernzeit", "ingestion", "dokumente",
                "organisation"):
        assert key not in TECHNICAL_PAGE_KEYS


def test_technical_override_css_unterdrueckt_farbverlauf_titel():
    css = _technical_override_css("#EAE9F7")
    assert "background:none !important" in css
    assert "#EAE9F7" in css


def test_technical_override_css_ist_gueltiger_style_block():
    css = _technical_override_css("#FDEFD2")
    assert css.strip().startswith("<style>")
    assert css.strip().endswith("</style>")


def test_doodle_layer_bleibt_fuer_normale_seiten_unveraendert():
    theme = theme_for("mindmap")
    html = _doodle_layer(theme["accent"], theme["soft"])
    assert "rag-doodle" in html
    assert theme["accent"] in html

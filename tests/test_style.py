"""Tests fuer ragapp.ui._style: reine String/Dict-Logik (kein Streamlit-Rendering).

Fokus dieser Datei: die "technische" Design-Variante fuer Evaluation/
Einstellungen (siehe TECHNICAL_PAGE_KEYS/_technical_override_css) - die
Betreiber-/Admin-Seiten sollen KEINE Doodles und eine entsaettigte, sachlichere
Karten-/Titel-Optik bekommen statt der verspielten "Cozy Kawaii"-Basis-Optik.
"""
from __future__ import annotations

from ragapp.ui._style import (
    HAMBURGER_KEYS,
    PAGE_REGISTRY,
    PAGE_THEMES,
    TECHNICAL_PAGE_KEYS,
    _command_palette_shortcut_html,
    _doodle_layer,
    _hero_title_html,
    _technical_override_css,
    celebration_effects_html,
    combo_pulse_html,
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


# --------------------------------------------------------------------------- #
# Gamification-Vertiefung: Sound/Vibration + Befehlspaletten-Sprungziel -
# reine String-Erzeugung, kein Streamlit-Rendering noetig (siehe Docstrings
# der jeweiligen Funktion fuer die Produktentscheidung dahinter).
# --------------------------------------------------------------------------- #
def test_celebration_effects_html_enthaelt_ton_und_vibration():
    html = celebration_effects_html()
    assert "<script>" in html and "</script>" in html
    assert "AudioContext" in html
    assert "vibrate" in html


def test_combo_pulse_html_enthaelt_nur_vibration_keinen_ton():
    html = combo_pulse_html()
    assert "vibrate" in html
    assert "AudioContext" not in html


def test_command_palette_shortcut_html_reagiert_auf_strg_oder_cmd_k():
    html = _command_palette_shortcut_html()
    assert "ctrlKey" in html and "metaKey" in html
    assert "'k'" in html
    assert "ragFocusSearch" in html
    # Regression: KEINE direkte Navigation (location.href=/location.assign)
    # aus dem sandboxed Iframe (siehe Docstring - wird vom Browser verweigert),
    # sondern ein echter Link-Klick (location.href darf als reiner LESE-Zugriff
    # vorkommen, z. B. als Basis-URL fuer new URL(...)).
    assert "location.href =" not in html and "location.assign" not in html
    assert ".click()" in html


# --------------------------------------------------------------------------- #
# PAGE_REGISTRY-Datenvalidierung - Grundlage der erweiterten Hamburger-
# Navigation (render_hamburger_nav() zeigt ALLE Seiten nach category
# gruppiert, siehe dortigen Docstring): eine fehlende/falsch geschriebene
# category wuerde eine Seite aus dem erweiterten Menue verschwinden lassen,
# ohne dass das beim Anschauen der Seite selbst auffaellt.
# --------------------------------------------------------------------------- #
def test_jede_seite_ausser_home_hat_eine_kategorie():
    for page in PAGE_REGISTRY:
        if page["key"] == "home":
            assert page["category"] is None
        else:
            assert page["category"], f"{page['key']} hat keine Kategorie"


def test_hamburger_keys_verweisen_auf_existierende_seiten():
    _keys = {p["key"] for p in PAGE_REGISTRY}
    for key in HAMBURGER_KEYS:
        assert key in _keys


def test_jede_seite_ist_genau_einmal_in_page_registry():
    _keys = [p["key"] for p in PAGE_REGISTRY]
    assert len(_keys) == len(set(_keys))


def test_kategorien_gruppieren_alle_nicht_home_seiten_lueckenlos():
    _by_category: dict[str, list[str]] = {}
    for page in PAGE_REGISTRY:
        if page["category"]:
            _by_category.setdefault(page["category"], []).append(page["key"])
    _grouped_keys = {k for keys in _by_category.values() for k in keys}
    _all_non_home = {p["key"] for p in PAGE_REGISTRY if p["key"] != "home"}
    assert _grouped_keys == _all_non_home


# --------------------------------------------------------------------------- #
# Handy-Optimierung: Hero-Titel darf nicht mehr mitten im Wort umbrechen
# (Live-Test bei 390px zeigte vorher "Willkommen zurü/ck", weil jeder
# Buchstabe sein eigenes inline-block-Element war) - siehe
# _hero_title_html()-Docstring.
# --------------------------------------------------------------------------- #
def test_hero_title_html_wrapt_jedes_wort_atomar():
    import xml.etree.ElementTree as ET
    html = _hero_title_html("Willkommen zurück")
    root = ET.fromstring(html)
    word_els = root.findall('.//span[@class="rag-hero-word"]')
    assert len(word_els) == 2
    # Jedes Wort-Span enthaelt NUR die Buchstaben dieses einen Wortes - kein
    # Leerzeichen/keine Trennung dazwischen, die der Browser als eigene
    # Umbruchstelle missverstehen koennte.
    rebuilt = ["".join(word.itertext()) for word in word_els]
    assert rebuilt == ["Willkommen", "zurück"]


def test_hero_title_html_erlaubt_umbruch_nur_zwischen_woertern():
    html = _hero_title_html("Eine Testüberschrift")
    # Zwischen den beiden Wort-Wrappern muss ein GANZ NORMALES, umbrechbares
    # Leerzeichen stehen (kein &nbsp;) - genau da DARF der Browser umbrechen.
    assert "</span> <span class=\"rag-hero-word\">" in html
    assert "&nbsp;" not in html


def test_hero_title_html_einzelnes_wort_hat_keine_luecke():
    html = _hero_title_html("Fortschritt")
    assert html.count('class="rag-hero-word"') == 1


def test_hero_title_html_ist_wohlgeformtes_xml():
    import xml.etree.ElementTree as ET
    html = _hero_title_html("Willkommen zurück 👋")
    ET.fromstring(html)

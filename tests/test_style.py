"""Tests fuer ragapp.ui._style: reine String/Dict-Logik (kein Streamlit-Rendering).

Fokus dieser Datei: die "technische" Design-Variante fuer Evaluation/
Einstellungen (siehe TECHNICAL_PAGE_KEYS/_technical_override_css) - die
Betreiber-/Admin-Seiten sollen KEINE Doodles und eine entsaettigte, sachlichere
Karten-/Titel-Optik bekommen statt der verspielten "Cozy Kawaii"-Basis-Optik.
"""
from __future__ import annotations

from ragapp.ui._style import (
    GOAL_CATEGORIES,
    GOAL_HUB_KEYS,
    HAMBURGER_KEYS,
    HIDDEN_PAGE_KEYS,
    HOME_PIN_KEYS,
    PAGE_REGISTRY,
    PAGE_THEMES,
    TECHNICAL_PAGE_KEYS,
    _command_palette_shortcut_html,
    _doodle_layer,
    _hero_title_html,
    _technical_override_css,
    _theme_toggle_html,
    _i18n_patch_html,
    _BASE_CSS,
    _FONT_FACE_CSS,
    celebration_effects_html,
    combo_pulse_html,
    page_title,
    theme_for,
)


def test_technical_page_keys_enthaelt_nur_evaluation_und_einstellungen():
    assert TECHNICAL_PAGE_KEYS == {"evaluation", "einstellungen"}


def test_technical_page_keys_sind_bekannte_themen():
    for key in TECHNICAL_PAGE_KEYS:
        assert key in PAGE_THEMES


def test_lern_und_erstellen_seiten_sind_nicht_technisch():
    for key in ("home", "chat", "lernen", "mindmap", "uebungsaufgaben",
                "lernplan", "zusammenfassung", "audio", "vortrag", "notizen",
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
    _keys = {p["key"]: p for p in PAGE_REGISTRY}
    for key in HAMBURGER_KEYS:
        assert key in _keys


def test_home_pin_keys_existieren_und_sind_alltagsrelevant():
    _keys = {p["key"] for p in PAGE_REGISTRY}
    for key in HOME_PIN_KEYS:
        assert key in _keys
    assert "lernen" in HOME_PIN_KEYS
    assert "fortschritt" in HOME_PIN_KEYS


def test_kurzwahl_und_home_pins_sind_die_fuenf_zielgruppen():
    assert list(GOAL_HUB_KEYS) == list(GOAL_CATEGORIES)
    assert HAMBURGER_KEYS == [GOAL_HUB_KEYS[c] for c in GOAL_CATEGORIES]
    assert HAMBURGER_KEYS == [
        "home", "organisation", "lernen", "notizen", "fortschritt",
    ]
    assert "chat" not in HAMBURGER_KEYS
    assert HOME_PIN_KEYS == [
        "lernplan", "organisation", "lernen", "notizen", "fortschritt",
    ]
    for key in ("zusammenfassung", "audio", "vortrag", "mindmap"):
        assert key not in HOME_PIN_KEYS
        assert key not in HAMBURGER_KEYS


def test_evaluation_ist_im_studenten_alltag_versteckt():
    assert "evaluation" in HIDDEN_PAGE_KEYS
    assert "evaluation" not in HOME_PIN_KEYS
    assert "evaluation" not in HAMBURGER_KEYS


def test_ingestion_heisst_import_lernen_heisst_karteikarten():
    assert page_title("ingestion").endswith("Import")
    assert "Karteikarten" in page_title("lernen")
    assert "Dokumente" in page_title("dokumente")
    assert "Semester einrichten" in page_title("semesterplan")
    assert "Audio-Übersicht" in page_title("audio")


def test_ingestion_ist_im_studenten_alltag_versteckt():
    assert "ingestion" in HIDDEN_PAGE_KEYS
    assert "ingestion" not in HOME_PIN_KEYS
    assert "ingestion" not in HAMBURGER_KEYS


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


def test_kategorien_sind_die_fuenf_zielgruppen_in_dieser_reihenfolge():
    assert GOAL_CATEGORIES == (
        "Heute", "Kurse", "Lernen", "Werkzeuge", "Fortschritt",
    )
    seen: list[str] = []
    for page in PAGE_REGISTRY:
        cat = page["category"]
        if cat and cat not in seen:
            seen.append(cat)
    assert seen == list(GOAL_CATEGORIES)
    for page in PAGE_REGISTRY:
        if page["key"] == "home":
            continue
        assert page["category"] in GOAL_CATEGORIES, page["key"]


def test_jede_zielgruppe_hat_mindestens_eine_sichtbare_seite():
    visible = [p for p in PAGE_REGISTRY
               if p["category"] and p["key"] not in HIDDEN_PAGE_KEYS]
    for cat in GOAL_CATEGORIES:
        assert any(p["category"] == cat for p in visible), cat


def test_kurse_haelt_stundenplan_semesterplan_und_dokumente():
    by_key = {p["key"]: p["category"] for p in PAGE_REGISTRY}
    assert by_key["organisation"] == "Kurse"
    assert by_key["semesterplan"] == "Kurse"
    assert by_key["dokumente"] == "Kurse"


def test_generatoren_gehoeren_zu_lernen():
    by_key = {p["key"]: p["category"] for p in PAGE_REGISTRY}
    for key in ("mindmap", "zusammenfassung", "audio", "vortrag"):
        assert by_key[key] == "Lernen"


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


# --------------------------------------------------------------------------- #
# Dark-Mode-Umschalter: der Klick-Handler darf NICHT einmalig auf dem Parent-
# document gebunden und danach per Flag uebersprungen werden. Streamlit
# unmountet das components.html-Iframe bei Navigation; der Browser verwirft
# dann den Listener, das Flag bleibt - Klicks tun danach nichts mehr.
# --------------------------------------------------------------------------- #
def test_theme_toggle_html_bindet_handler_am_button_neu():
    html = _theme_toggle_html()
    assert "parent.localStorage" in html
    assert "btn.onclick" in html
    assert "__ragThemeClickBound" not in html
    assert "btn.type = 'button'" in html
    assert "rag-theme-switch" in html


def test_theme_toggle_html_nutzt_parent_matchmedia_und_parent_timer():
    html = _theme_toggle_html()
    assert "parent.matchMedia" in html
    assert "parent.setInterval" in html
    assert "rag-theme-switch" in html


def test_theme_toggle_meldet_dunkelmodus_an_screenreader():
    html = _theme_toggle_html()
    assert "aria-pressed" in html
    assert "aria-label" in html


def test_basis_css_hat_fokus_kontrast_und_reduced_motion():
    assert ":focus-visible" in _BASE_CSS
    assert "prefers-reduced-motion" in _BASE_CSS
    assert "color-scheme:light" in _BASE_CSS
    assert "touch-action:manipulation" in _BASE_CSS
    assert "splan-tl-label" in _BASE_CSS
    assert "notiz-item-meta" in _BASE_CSS
    assert "rag-tt-today-tag" in _BASE_CSS


def test_ziffern_und_handy_hero_bleiben_lesbar():
    assert "overflow-wrap: anywhere" not in _FONT_FACE_CSS
    assert "lining-nums proportional-nums" not in _FONT_FACE_CSS
    assert "font-variant-numeric: normal" in _FONT_FACE_CSS
    assert "font-variant-emoji: text" in _FONT_FACE_CSS
    assert "html, body { font-variant-emoji: emoji; }" not in _FONT_FACE_CSS
    assert "st-key-mascot_hero" in _BASE_CSS
    assert "rag-heute-date" in _BASE_CSS
    _BASE_CSS.format(accent="#c43b58", soft="#f6d5dc")


def test_i18n_patch_uebersetzt_englische_widget_reste():
    html = _i18n_patch_html()
    assert "Choose options" in html
    assert "Auswählen" in html
    assert "Datei hierher ziehen" in html


def test_seitenstart_klappt_die_sidebar_zu():
    import inspect
    from ragapp.ui._loading import page_boot
    assert 'initial_sidebar_state="collapsed"' in inspect.getsource(page_boot)


def test_hamburger_zeigt_seitentitel_statt_gruppennamen():
    import inspect
    from ragapp.ui._style import render_hamburger_nav
    src = inspect.getsource(render_hamburger_nav)
    assert 'shown = "Heute" if key == "home" else page["title"]' in src
    assert '_p["key"] in HIDDEN_PAGE_KEYS or _p["key"] in HAMBURGER_KEYS' in src
    assert "Schnellzugriff" in src
    assert "render_session_controls" in src
    assert "Sitzung" in src


def test_delete_button_oeffnet_gemeinsamen_dialog():
    import inspect
    from ragapp.ui import _style
    assert _style._DELETE_PENDING == "_rag_delete_pending"
    src = inspect.getsource(_style.delete_button)
    assert "_DELETE_PENDING" in src
    dialog = inspect.getsource(_style._shared_delete_dialog)
    assert "Jetzt löschen" in dialog
    assert "Abbrechen" in dialog
